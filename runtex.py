#!env python3
# -*- coding: utf-8 -*-
# Time-Stamp: <2016-05-09 00:18:33>

product_name = 'RunTeX'
version      = '0.0.0'

latexmk      = 'latexmk'

import os
import sys
import re
import shutil
import tempfile
import argparse
import configparser
import textwrap
import subprocess

class Color:
    r = '\033[91m'
    g = '\033[92m'
    b = '\033[94m'
    y = '\033[93m'
    s = '\033[96m'
    end = '\033[0m'

    @classmethod
    def red(self, str):
        return self.r + str + self.end
    @classmethod
    def green(self, str):
        return self.g + str + self.end
    @classmethod
    def blue(self, str):
        return self.b + str + self.end
    @classmethod
    def yellow(self, str):
        return self.y + str + self.end
    @classmethod
    def sky(self, str):
        return self.s + str + self.end


def check_latexmk():
    if not shutil.which(latexmk):
        raise Exception('latexmk not found.')
    pass

def check_texfile(texfile_path, basedir = "."):
    """Check that ``texfile_path``, relative to ``basedir``, exists and a
    correct extention of ``.tex``.
    Returns *stem* of ``texfile_path``.
    """
    if not texfile_path.endswith('.tex'):
        raise Exception('texfile must have suffix ".tex"')
    if not os.path.exists(os.path.join(basedir or ".", texfile_path)):
        raise Exception('specified texfile not found.')
    return os.path.basename(texfile_path)[0:-4]

def check_absence(path):
    """Check that ``path`` does not exists.
    """
    if os.path.lexists(path):
        raise Exception('{} already exists.'.format(path))
    pass

def remove_file(path):
    """Remove the **file** if exists.
    """
    if os.path.exists(path):
        os.remove(path)
    pass

def get_dependencies(texfile_name, basedir = '.'):
    print("\n\n" + Color.green("Check dependency of " + Color.b + texfile_name + Color.g + "."))

    output, stderr = subprocess.Popen(
            [latexmk, '-g', '-deps', '-bibtex-', '-interaction=nonstopmode', '-quiet', texfile_name],
            stdout = subprocess.PIPE,
            cwd = basedir or '.').communicate()

    begin_tag = '#===Dependents for '
    end_tag   = '#===End dependents for '
    dep = output.decode("utf-8") 
    dep = dep[dep.index(begin_tag) : ]
    dep = dep[0 : dep.rindex(end_tag)-1]
    # For begin_tag, exclude zero because it does exist at zero.
    if dep.rfind(begin_tag) > 0 or dep.find(end_tag) >= 0:
        raise Exception("Dependency cannot resolved")
    dep = dep.splitlines()[2:] # first two lines are removed

    dep = [x.lstrip("\n\r \t").rstrip("\n\r \t\\") for x in dep]
    localdep = list(set([os.path.normpath(x) for x in dep if x.find(os.path.sep + "texmf") == -1]))
    localdep = [x for x in localdep if x != texfile_name]
    return localdep



# 'path' means full-path from a base (usually the currrent) directory to the file/dir.
# 'stem' is a basename of file, with no dir, and no "extension".
# 'name' is a basename of file including extension, and possibly with dir.

def compile(texfile_path, basedir = '.', remove_misc = False, quiet = False):
    basedir = basedir or '.'
    check_latexmk()
    texfile_stem = check_texfile(texfile_path, basedir)

    print("\n\n" + Color.green("Compile " + texfile + " in " + Color.b + basedir + Color.g + "."))
    subprocess.Popen([latexmk, '-pdf', '-quiet' if quiet else '', texfile_path], cwd = basedir).communicate()

    if remove_misc:
        print("\n\n" + Color.green("Unnecessary files in " + Color.b + basedir + Color.g + " are removed."))
        tempdir  = tempfile.mkdtemp()
        shelters = {}
        # pdf and bbl are created in ``basedir``
        for ext in [".pdf", "bbl"]:
            src = os.path.join(basedir, texfile_stem + ext)
            dst = os.path.join(tempdir, os.path.basename(src))
            if os.path.exists(src):
                shelters[src] = dst
        for src in shelters.keys():
            shutil.move(src, tempdir)
        subprocess.Popen([latexmk, '-CA', texfile_path], cwd = basedir).communicate()
        for dst in shelters.values():
            shutil.move(dst, basedir)
        os.rmdir(tempdir)


def archive(src_tex_path, suffix = "", style = None):
    '''Create an archive file ``stem.tar.gz`` etc., where ``stem`` is the
    basename of ``src_tex_path`` without extension with ``suffix``.

    Following are generated:
      * ``stem.tar.gz`` contains required files and ``.bbl`` file.
      * ``stem.withpdf.tar.gz`` contains generated pdf as well.
      * ``stem`` directory is also created as a working directory.

    For example, for ``foo/bar.tex`` and ``_v1`` as the suffix, there will be
      * ``bar_v1/foo/bar_v1.tex`` and relevant files
      * ``bar_v1/bar_v1.bbl``
      * ``bar_v1.pdf``
      * ``bar_v1.tar.gz``
      * ``bar_v1.withpdf.tar.gz``
    '''

    check_latexmk()
    dst_tex_stem = check_texfile(src_tex_path) + (suffix or "")
    names = {}
    names["tempdir"] = dst_tex_stem
    names["texfile"] = os.path.join(os.path.dirname(src_tex_path), dst_tex_stem + ".tex")
    names["pdffile"] = dst_tex_stem + ".pdf"
    if style == "JHEP":
        names["archive"] = dst_tex_stem + ".JHEP.tar.gz"
        names["arcwpdf"] = dst_tex_stem + ".JHEP_withpdf.tar.gz"
    else:
        names["archive"] = dst_tex_stem + ".tar.gz"
        names["arcwpdf"] = dst_tex_stem + ".withpdf.tar.gz"

    dst_path = lambda tag: os.path.join(names["tempdir"], names[tag])

    # files created in the current directory
    for tag in ["tempdir", "pdffile", "archive", "arcwpdf"]:
        check_absence(names[tag])

    os.makedirs(os.path.dirname(dst_path("texfile")), exist_ok = True)
    shutil.copy(src_tex_path, dst_path("texfile"))
    dependents = get_dependencies(names["texfile"], names["tempdir"])
    for src in dependents:
        if os.path.exists(src):
            dst = os.path.join(names["tempdir"], src)
            os.makedirs(os.path.dirname(dst), exist_ok = True)
            shutil.copy(src, dst)
        else:
            # FileNotFound should be treated by TeX compiler.
            # Just ignore it here.
            pass

    compile(names["texfile"], names["tempdir"], remove_misc = True, quiet = True)

    if style == "JHEP":
        basedir = names["tempdir"]
        names["arcwpdf"] = os.path.join("..", names["arcwpdf"])
        names["archive"] = os.path.join("..", names["archive"])
        targets = lambda: os.listdir(names["tempdir"])
    else:
        basedir = '.'
        targets = lambda: [names["tempdir"]]

    print("\n\n" + Color.green("Compressing into " + Color.b + names["arcwpdf"] + Color.g + " with PDF."))
    subprocess.Popen(['tar', 'czvf', names["arcwpdf"]] + targets(), cwd = basedir).communicate()

    shutil.move(dst_path("pdffile"), '.')

    print("\n\n" + Color.green("Compressing into " + Color.b + names["archive"] + Color.g + " without PDF."))
    subprocess.Popen(['tar', 'czvf', names["archive"]] + targets(), cwd = basedir).communicate()

    if style == "JHEP":
        print("\n" + Color.green("The archives are without top directory, ready for JHEP-submission."))


def push(texfile, remotedir, suffix = None):
    pass

def pull(texfile, remotedir, suffix = None):
    pass


if __name__ == '__main__':
    iniparser = configparser.ConfigParser()
    iniparser.read('runtex.ini')
    texfile_ini = iniparser.get('main', 'texfile',   fallback=None)
    remotedir   = iniparser.get('main', 'remotedir', fallback=None)
    if remotedir and remotedir.endswith('/'):
        remotedir = remotedir[0:-1]

    epilog = """\
    --tex texfile  specity main tex file%(texreq)s
    -h, --help     show this help message and exit
    -V             show program's version number and exit
    
    %(prog)s compile          compile %(tex)s
    %(prog)s archive suffix   compile and make %(tgz)s
    %(prog)s JHEP suffix      compile and make %(tgz)s (JHEP)

    """
    if not texfile_ini:
        epilog += """
    Note: <texfile> and <remotedir> are recommended to be configured in runtex.ini, as
      [main]
      texfile   = greatproject.tex
      remotedir = ~/Dropbox/greatproject_draft
    """
    elif remotedir:
        epilog += """
    %(prog)s push [suffix]    compile and copy related files to %(remote)s
                                      If suffix is specified, tex/pdf/bbl are renamed to
                                      %(rename)s.
    %(prog)s pull [suffix]    remove all files and pull from %(remote)s."""
    
    if texfile_ini:
        if not texfile_ini.endswith('.tex'):
            raise Exception('texfile must have suffix ".tex"')
        tex    = Color.green(texfile_ini)
        tgz    = Color.green(texfile_ini[0:-4] + '<suffix>.tar.gz')
        texreq = ", overriding the default value"
        remote = Color.blue(remotedir) if remotedir else None
        rename = Color.green(texfile_ini[0:-4] + '<suffix>.{tex,pdf,bbl}')
    else:
        tex    = "<texfile>"
        tgz    = "<texfile><suffix>.tar.gz"
        texreq = Color.yellow(" (required)")
        remote = None
        rename = None

    epilog = epilog % { "prog": sys.argv[0], "tex": tex, "tgz": tgz, "texreq": texreq, "remote": remote, "rename": rename }

    argparser = argparse.ArgumentParser(
            add_help=False,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            usage = "%(prog)s [-h] [-V] [--tex texfile] command ...",
            epilog=textwrap.dedent(epilog))
    argparser.add_argument("--tex", metavar="texfile", help=argparse.SUPPRESS)
    argparser.add_argument("command", help=argparse.SUPPRESS)
    argparser.add_argument("option", nargs=argparse.REMAINDER, metavar='...', default=None, help=argparse.SUPPRESS)
    argparser.add_argument("-h", action='help', default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    argparser.add_argument("-V", action='version', version=productname + " " + version, help=argparse.SUPPRESS)
    args = argparser.parse_args()

    texfile = args.tex or texfile_ini or None
    if not texfile:
        raise Exception('texfile not specified; see help')
    if not texfile.endswith('.tex'):
        raise Exception('texfile must have suffix ".tex"')
        
    n_opt = len(args.option)
    args.option  += [None]
    if args.command == "compile" and n_opt == 0:
        compile(texfile)
    elif args.command == "archive" and n_opt <= 1:
        archive(texfile, suffix = args.option[0])
    elif args.command == "JHEP" and n_opt <= 1:
        archive(texfile, suffix = args.option[0], style = "JHEP")
    elif args.command == "pull" and n_opt <= 1:
        pull(texfile, remotedir, suffix = args.option[0])
    elif args.command == "push" and n_opt <= 1:
        push(texfile, remotedir, suffix = args.option[0])
    else:
        argparser.parse_args(["-h"])
