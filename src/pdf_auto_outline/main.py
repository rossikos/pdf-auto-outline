import pymupdf.layout
from time import perf_counter
from multiprocessing import Pool
import os
import subprocess
import argparse
import tempfile

SIOYEK = None

def log(message, end='\n'):
    if SIOYEK:
        SIOYEK.set_status_string(message)
    else:
        print(message, end=end)

def get_md5_hash(path):
    import hashlib
    m = hashlib.md5()
    with open(path, 'rb') as f:
        m.update(f.read())
    return m.hexdigest()

def sioyek_transfer_annots(shared_db_path, from_hash, to_hash):
    import sqlite3
    con = sqlite3.connect(shared_db_path)
    try:
        with con:
            con.execute("UPDATE highlights SET document_path = (?) WHERE document_path == (?)", (to_hash, from_hash))
        log(f'moved highlights from {from_hash} to {to_hash}')
    except Exception as e:
        log(f'failed to move highlights from {from_hash} to {to_hash}: {e}')

    con.close()


def process_pg(fpath, pg_num) -> tuple[int, list[list]]:
    pg = pymupdf.open(fpath)[pg_num]
    pg.get_layout()

    page_toc_entries = []

    def get_text(boxclass, j, pg):
        text = pg.get_textbox(pymupdf.Rect(*j[:4])).replace('\n', ' ').strip()
        if boxclass == 'caption':
            a = text.find('.', 15)
            return text[:a] or text
        return text

    page_toc_entries = [
            [1, get_text(j[4], j, pg), pg_num+1, j[1]]
            for j in pg.layout_information if j[4] in ('section-header', 'caption')
    ]

    return pg_num, page_toc_entries

def process_pg_wrapper(args):
    return process_pg(args[0], args[1])

def generate_toc_nnet(pdfpath, worker_cnt=3) -> list:
    doc = pymupdf.open(pdfpath)
    pg_cnt = doc.page_count
    pg_nums = range(pg_cnt)
    doc.close()

    try:
        if worker_cnt < 2:
            log('Started..')
            count = 1
            bar = 50
            entries = []
            for i in pg_nums:
                for j in process_pg(pdfpath, i)[1]:
                    entries.append(j)
                progress = (count * bar) // (pg_cnt)
                log(f"[{'='*(progress)}{' '*(bar - progress)}] {count}/{pg_cnt} pages", end='\r')
                count += 1

            return entries


        with Pool(processes=worker_cnt) as pool:
            log("Started..")
            count = 1
            bar = 50
            results = {}
            tasks = [(pdfpath, i) for i in pg_nums]
            result_iter = pool.imap_unordered(process_pg_wrapper, tasks)
            for pg_num, res in result_iter:
                results[pg_num] = res

                progress = (count * bar) // (pg_cnt)
                log(f"[{'='*(progress)}{' '*(bar - progress)}] {count}/{pg_cnt} pages", end='\r')
                count += 1
    except KeyboardInterrupt:
        log('\nCancelled')
        exit()


    return [j for i in pg_nums for j in results[i]]

def align_toc_lvls(toc_entries: list) -> list:
    import re
    def act(current): # cur prev expected lvl
        if current == d['prev_name']: # current is sibling
            pass
        elif current == 'p5': # current is figure/table type
            d['lvl'] += 1
        elif e[current] < d['prev_lvl']: # current is parent
            d['lvl'] = e[current]
        else: # e[current] > prev[1]: # current is child
            e[current] = min(d['lvl'] + 1, e[current])
            d['lvl'] = min(d['lvl'] + 1, e[current])

        d['prev_name'] = current
        d['prev_lvl'] = e[current]
        toc_entries[i-d['removed']][0] = d['lvl']

    p1 = re.compile(r'^[A-Z\d]')
    patterns = (
        re.compile(r'^(Contents)|(Chapter)|(Appendix)|(Index)|(Bibliography)|(Preface)'),
        re.compile(r'^([IVXC\d])+\.[IVXC\d]\.? \w'),
        re.compile(r'^([AIVXC\d]+\.){2}[IVXC\d]\.? \w'),
        re.compile(r'^(Fig(ure)?\.?)|(Table\.? [\dIVXC]+)', re.IGNORECASE),
        re.compile(r'''\d?\s?(Introduction)|((Materials? and )?Methods)|(Results)|
                        (Discussion)|(References)|(Summary)|(Conclusion)|(Acknowledgements)
                        ''', re.IGNORECASE),
        re.compile(r'^\d?\s?[A-Z ]{2,}'),
    )

    # expected nesting levels
    e = {'p1': 1, 'p2': 1, 'p3': 2, 'p4': 3, 'p5': 5, 'p6': 1, 'p7': 1, 'l': 2,}
    # line status
    d = {'lvl': 1, 'prev_name': 'p1', 'prev_lvl': 1, 'titles': set(), 'removed': 0}

    log('aligning levels..')

    for i in range(1, len(toc_entries)):
        title = toc_entries[i-d['removed']][1]
        if (not p1.match(title)) or len(title) < 4 or title in d['titles']: #skip
            toc_entries.pop(i-d['removed'])
            d['removed'] += 1
        elif (name := next((idi for idi, i in enumerate(patterns) if i.match(title)), None)):
            act(f'p{name+2}')
        else:
            d['titles'].add(title)
            act('l')

    return toc_entries

def get_tmpfile():
    return tempfile.NamedTemporaryFile(
            mode='w+', encoding='utf-8', delete=False, suffix='.txt'
            )

def generate_txtfile(toc_entries, txtfile=get_tmpfile()):
    import textwrap
    txt = textwrap.dedent("""\
    ============================================================
                     TABLE OF CONTENTS OUTLINE
    4spaces/lvl text  |  pg#  |  {details dictionary} OR y-coord

       Type 'C' as the first character of this file to cancel
    ============================================================

    """)
    if not toc_entries:
        pass
    elif len(toc_entries[0]) > 3:
        txt += '\n'.join(f"{' '*4 * (i[0] - 1)}{i[1]}  |  {i[2]}  |  {i[3]}" 
                        for i in toc_entries)
    else:
        txt += '\n'.join(f"{' '*4 * (i[0] - 1)}{i[1]}  |  {i[2]}"
                        for i in toc_entries)

    txtfile.write(txt)
    txtfile.flush()
    txtfile.seek(0)

    return txtfile



def parse_txtfile(f, tablevel=2) -> list:
    toc_entries = []
    if (c := f.read(1)) == 'C':
        log('Outline not written')
        exit()
    elif c == '=':
        lines = f.readlines()[7:]
    else: lines = f.read()

    for i in lines:
        i = i.replace('\t', '    '*tablevel)
        lvl = (len(i) - len(i.lstrip())) // 4 + 1
        a = i.lstrip().split('  |  ')
        if len(a) < 3:
            toc_entries.append(
                    [lvl, a[0], int(a[1])] 
            )
        else:
            toc_entries.append(
                    [lvl, a[0], int(a[1]), eval(a[2])]
            )
    
    f.close()

    return toc_entries

def embed_toc(pdfpath, toc_entries, newfile=''):
    doc = pymupdf.open(pdfpath)
    doc.set_toc(toc_entries, collapse=2)
    if newfile:
        doc.save(newfile)
        log(f"toc written to '{newfile}'")
    else:
        doc.saveIncr()
        log(f"toc saved to '{pdfpath}'")

def get_toc_custom(doc) -> list:
    toc_entries = [[*i[:3], i[3].get('to')[1]] for i in doc.get_toc(False)]
    return toc_entries

def edit_txtfile(f):
    if os.name == 'nt':
        subprocess.run(['start', '/WAIT', f.name], shell=True)
    else: # name == 'posix':
        editor = os.environ.get('EDITOR', 'vi')  
        subprocess.run([editor, f.name])

def main():
    parser = argparse.ArgumentParser(prog='pdfao')
    parser.add_argument("filename", help='input pdf')
    parser.add_argument('-s', '--straight', action='store_true', help="write toc straight to pdf; skip editing")
    parser.add_argument('-o', '--out', type=str, metavar='<path>', help='write changes to new pdf')
    parser.add_argument('-mp', '--multiprocess', type=int, metavar='<n>', help='spread job over n processes (faster on linux)', default=1)
    parser.add_argument('-e', '--edit', action='store_true', help='edit pdf toc')
    parser.add_argument('-se', '--superedit', action='store_true', help='edit pdf toc (more attibutes available)')
    parser.add_argument('-i', '--infile', type=str, metavar='<file>', help='write toc from file to pdf')
    parser.add_argument('-t', '--tablevel', type=int, metavar='<n>', help='tab = n toc nesting levels (default 2)', default=2)
    parser.add_argument('--sioyek', type=str, metavar='<path>', help='for users of the Sioyek pdf viewer')
    parser.add_argument('--version', action='version', version='%(prog)s 0.1.6')

    args = parser.parse_args()

    if args.out:
        args.out = os.path.join(
                os.path.dirname(args.filename),
                args.out)

    if args.sioyek:
        from sioyek.sioyek import Sioyek
        global SIOYEK
        SIOYEK = Sioyek(args.sioyek)
        # local_db = args.sioyek[1]
        # shared_db = args.sioyek[2]
        # pdf_path = args.sioyek[3]
        # from_hash = get_md5_hash(args.filename)

    if args.edit or args.superedit:
        doc = pymupdf.Document(args.filename)
        if args.superedit:
            f = generate_txtfile(doc.get_toc(False))
        else:
            f = generate_txtfile(get_toc_custom(doc))
        edit_txtfile(f)
        toc_entries = parse_txtfile(f, args.tablevel)
        embed_toc(args.filename, toc_entries, args.out)
        os.remove(f.name)
    elif args.infile:
        toc_entries = parse_txtfile(open(args.infile, encoding='utf-8'), args.tablevel)
        embed_toc(args.filename, toc_entries, args.out)
    else: # generate toc
        start = perf_counter()
        toc_entries = generate_toc_nnet(args.filename, args.multiprocess)
        end = perf_counter()
        log('')
        log(f"finished in {end - start:<4.1f} s")
        toc_entries = align_toc_lvls(toc_entries)
        if args.straight:
            embed_toc(args.filename, toc_entries, args.out)
        else:
            f = generate_txtfile(toc_entries)
            edit_txtfile(f)
            toc_entries = parse_txtfile(f, args.tablevel)
            embed_toc(args.filename, toc_entries, args.out)
            os.remove(f.name)

    # if args.sioyek and not args.out:
    #     to_hash = get_md5_hash(args.filename)
    #     sioyek_transfer_annots(shared_db, from_hash, to_hash)

