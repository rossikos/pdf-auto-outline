# PDF Auto Outline

A simple python program to automatically generate and embed a table of contents or outline in a PDF.

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
                        spread job over n processes (faster on linux)
  -e, --edit            edit pdf toc
  -se, --superedit      edit pdf toc (more attibutes available)
  -i, --infile <file>   write toc from file to pdf
  -t, --tablevel <n>    tab = n toc nesting levels (default 2)
  --sioyek <path>       for users of the Sioyek pdf viewer
  --version             show program's version number and exit
```

## For Sioyek Users

Example commands; add to prefs_user.config.

```
new_command _gen_toc python3 path/to/pdfao.py "%{file_path}" --sioyek path/to/sioyek -mp 4
new_command _edit_toc python3 path/to/pdfao.py "%{file_path}" --sioyek path/to/sioyek -e
```


