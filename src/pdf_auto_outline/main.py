import pymupdf.layout
from pymupdf import Point
from time import perf_counter
from multiprocessing import Pool
import os
import subprocess
import argparse

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

    log('')

    return [j for i in pg_nums for j in results[i]]

def align_toc_lvls(toc_entries: list) -> list:
    # TODO: fix this spaghetti
    import re
    def act(lvl, current, prev): # cur prev expected lvl
        # if current == prev - 1: # current is parent
        if current == prev[0]: # current is sibling
            return lvl
        elif current == 'p5':
            return lvl + 1
        elif e[current] < prev[1]: # current is parent
            return e[current]
            # return max(1, lvl - 1)
        else: # e[current] > prev[1]: # current is child
            e[current] = min(lvl + 1, e[current])
            return min(lvl + 1, e[current])
        # else: #e[current] == prev: # current is sibling
        #     return lvl

    p1 = re.compile(r'^[A-Z\d]')
    p2 = re.compile(r'^(Contents)|(Chapter)|(Appendix)|(Index)|(Bibliograph)|(Preface)')
    p3 = re.compile(r'^([IVXC\d])+\.[IVXC\d]\.? \w')
    p4 = re.compile(r'^([AIVXC\d]+\.){2}[IVXC\d]\.? \w')
    p5 = re.compile(r'^(Fig(ure)?\.?)|(Table\.? [\dIVXC]+)')
    p6 = re.compile(r'''\d?\s?(Introduction)|((Materials and )?Methods)|(Results)|
                    (Discussion)|(References)|(Summary)|(Conclusion)|(Acknowledgements)
                    ''', re.IGNORECASE)
    p7 = re.compile(r'^\d?\s?[A-Z ]{2,}') 

    e = {'p1': 1, 'p2': 1, 'p3': 2, 'p4': 3, 'p5': 5, 'p6': 1, 'p7': 1, 'l': 2,}

    log('aligning levels..')
    lvl, prev, titles, removed = 1, ('p1', 1), set(), 0

    for i in range(1, len(toc_entries)):
        title = toc_entries[i-removed][1]
        if (not p1.match(title)) or len(title) < 4 or title in titles: #skip
            toc_entries.pop(i-removed)
            removed += 1
        elif p2.match(title):
            lvl = act(lvl, 'p2', prev)
            toc_entries[i-removed][0] = lvl
            prev = ('p2', e['p2'])
        elif p7.match(title):
            lvl = act(lvl, 'p7', prev)
            toc_entries[i-removed][0] = lvl
            prev = ('p7', e['p7'])
        elif p6.match(title):
            lvl = act(lvl, 'p6', prev)
            toc_entries[i-removed][0] = lvl
            prev = ('p6', e['p6'])
        elif p3.match(title):
            lvl = act(lvl, 'p3', prev)
            toc_entries[i-removed][0] = lvl
            prev = ('p3', e['p3'])
        elif p4.match(title):
            lvl = act(lvl, 'p4', prev)
            toc_entries[i-removed][0] = lvl
            prev = ('p4', e['p4'])
        elif p5.match(title):
            lvl = act(lvl, 'p5', prev)
            toc_entries[i-removed][0] = lvl
            prev = ('p5', e['p5'])
        else:
            titles.add(title)
            lvl = act(lvl, 'l', prev)
            toc_entries[i-removed][0] = lvl
            prev = ('l', e['l'])
    return toc_entries

def generate_txtfile(toc_entries, txtfile='outline.txt') -> str:
    import textwrap
    txt = textwrap.dedent("""\
    ============================================================
                     TABLE OF CONTENTS OUTLINE
    4spaces/lvl text  |  pg#  |  {details dictionary} OR y-coord
    ============================================================

    """)
    if len(toc_entries[0]) > 3:
        txt += '\n'.join(f"{' '*4 * (i[0] - 1)}{i[1]}  |  {i[2]}  |  {i[3]}" 
                        for i in toc_entries)
    else:
        txt += '\n'.join(f"{' '*4 * (i[0] - 1)}{i[1]}  |  {i[2]}"
                        for i in toc_entries)

    with open(txtfile, 'w', encoding='utf-8') as f:
        f.write(txt)

    return txtfile


def parse_txtfile(txtfile='outline.txt', tablevel=2) -> list:
    toc_entries = []
    with open(txtfile) as f:
        if f.read(1) == '=':
            lines = f.readlines()[5:]
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

    return toc_entries

def embed_toc(pdfpath, toc_entries, newfile=''):
    print(len(toc_entries))
    doc = pymupdf.open(pdfpath)
    doc.set_toc(toc_entries, collapse=2)
    if newfile:
        doc.save(newfile)
        log(f"toc written to '{newfile}'")
    else:
        doc.saveIncr()
        log(f"toc saved to '{pdfpath}'")



def edit_txtfile(txtfile='outline.txt'):
    editor = os.environ.get('EDITOR', 'notepad' if os.name == 'nt' else 'vi')
    subprocess.run([editor, txtfile])

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
    parser.add_argument('--version', action='version', version='%(prog)s 0.1.0')

    args = parser.parse_args()

    if args.sioyek:
        from sioyek.sioyek import Sioyek
        sioyek_path = args.sioyek[0]
        SIOYEK = Sioyek(sioyek_path)
        # local_db = args.sioyek[1]
        # shared_db = args.sioyek[2]
        # pdf_path = args.sioyek[3]
        # from_hash = get_md5_hash(args.filename)

    if args.edit or args.superedit:
        doc = pymupdf.Document(args.filename)
        generate_txtfile(doc.get_toc(not args.superedit))
        edit_txtfile()
        toc_entries = parse_txtfile(tablevel=args.tablevel)
        embed_toc(args.filename, toc_entries, args.out)
    elif args.infile:
        toc_entries = parse_txtfile(args.infile, args.tablevel)
        embed_toc(args.filename, toc_entries, args.out)
    else: # generate toc
        start = perf_counter()
        toc_entries = generate_toc_nnet(args.filename, args.multiprocess)
        end = perf_counter()
        log(f"finished in {end - start:<4.1f} s")
        toc_entries = align_toc_lvls(toc_entries)
        if args.straight:
            embed_toc(args.filename, toc_entries, args.out)
        else:
            generate_txtfile(toc_entries)
            edit_txtfile()
            toc_entries = parse_txtfile(tablevel=args.tablevel)
            embed_toc(args.filename, toc_entries, args.out)

    # if args.sioyek and not args.out:
    #     to_hash = get_md5_hash(args.filename)
    #     sioyek_transfer_annots(shared_db, from_hash, to_hash)

