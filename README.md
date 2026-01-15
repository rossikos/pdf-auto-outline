# PDF Auto Outline

Automatically generate and embed a table of contents or outline in a PDF.

Install: `python -m pip install pdf-auto-outline`

Suggestions and contributions are welcome.

## Usage

```
usage: pdfao [-h] [-s] [-o <path>] [-mp <n>] [-e] [-se] [-i <file>] [-t <n>] [--sioyek <path>] [--version] filename

positional arguments:
  filename              input pdf

options:
  -h, --help            show this help message and exit
  -s, --straight        write toc straight to pdf; skip editing
  -o, --out <path>      write changes to new pdf
  -mp, --multiprocess <n>
                        spread job over n processes (faster on Linux)
  -e, --edit            edit pdf toc
  -se, --superedit      edit pdf toc (more attibutes available)
  -i, --infile <file>   write toc from file to pdf
  -t, --tablevel <n>    tab = n toc nesting levels (default 2)
  --sioyek <path>       for users of the Sioyek pdf viewer
  --version             show program's version number and exit
```

### Examples

Generate toc and edit before saving:
`pdfao paper.pdf`

Generate and save to new pdf:
`pdfao paper.pdf -o new.pdf`

Edit exiting pdf toc:
`pdfao paper.pdf -e`

A save toc to new pdf from file:
`pdfao paper.pdf -o new.pdf -i outline.txt`


## For Sioyek Users

Example commands; add to `prefs_user.config`.

```
new_command _gen_toc pdfao "%{file_path}" --sioyek path/to/sioyek -mp 4
new_command _edit_toc pdfao path/to/pdfao.py "%{file_path}" --sioyek path/to/sioyek -se
```

If you don't wish to install from PyPI, download source and use `python3 -m path/to/src/pdf_auto_outline` in place of `pdfao`.

