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

> [!NOTE]
> Multiprocessing on Windows and MacOS is considerably slower than on Linux. Users are encouraged to test and see what works best for them.

### Examples

Generate toc and edit before saving:
`pdfao paper.pdf`

Generate and save to new pdf:
`pdfao paper.pdf -o new.pdf`

Edit exiting pdf toc:
`pdfao paper.pdf -e`

A save toc to new pdf from file:
`pdfao paper.pdf -o new.pdf -i outline.txt`

### Editing

The edit command opens the TOC in the OS default editor (result of 'start' command on Windows and 'EDITOR' environment variable on MacOS and Linux). The file schema is something like this:

```
Title 1  |  1
    Title 2  |  2  |  *
                 ^^^^^^
				 optional		
```
The essential parts of each line are:
- Indentation - 4 space characters per nesting level (or use tabs with the -t flag).
- Title text
- Delimiter - '  |  ' (vertical bar with 2 spaces padding on each side)
- Page number

The optional part can be one of:
```
  |  None                  	same as not including it   
  |  241.2					y-ordinate 
  |  {<dictionary>}			dictionary with more attributes for the ToC entry
```

## For Sioyek Users

Example commands; add to `prefs_user.config`.

```
new_command _gen_toc pdfao "%{file_path}" --sioyek path/to/sioyek -mp 4
new_command _edit_toc pdfao "%{file_path}"
```

The sioyek library and flag are optional; they allow logging to the status bar. This is more useful for ToC generation where you may want a progress bar. 

If you don't wish to install from PyPI, download source and use `python3 -m path/to/src/pdf_auto_outline` in place of `pdfao`.

