#!env python3
# -*- coding: utf-8 -*-
# Time-Stamp: <2016-05-09 14:38:33>

product_name = 'RunTeX'
version      = '0.0.1'

latexmk      = 'latexmk'
config_file  = 'runtex.conf'

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



def error(text):
    print(Color.red('\n[ERROR] ' + text))
    sys.exit(1)

def warning(text):
    print(Color.yellow('\n[Warning] ' + text))

def copy_with_mkdir(src, dst):
    dirname = os.path.dirname(dst)
    if dirname and not os.path.isdir(dirname):
        os.makedirs(dirname, exist_ok = True)
    return shutil.copy2(src, dst)



def usage(message = None):
    text = """usage: {this} [-h] [-V] command ...

-h, --help  show this help message and exit
-V          show program's version number and exit

available commands:
    {this} compile          compile {g}{tex}{e}
    {this} archive suffix   compile and create {g}{tgz}{e}
    {this} JHEP suffix      compile and create {g}{tgz}{e} (JHEP)"""

    if config["remotedir"]:
        text += """
    {this} push [suffix]    compile and copy relevant files to {g}{remote}{e}
    {this} pull [suffix]    pull files with <suffix> from {g}{remote}{e}"""
    else:
        text += """
    {this} push [suffix]    available with {y}remotedir{e} option.
    {this} pull [suffix]    available with {y}remotedir{e} option."""

    print(text.format(
        this = os.path.basename(sys.argv[0]),
        g = Color.g,
        y = Color.y,
        e = Color.end,
        tex = config["texfile"],
        remote = config["remotedir"],
        tgz = config["texfile"][0:-4] + "<suffix>.tar.gz",
    ))

    if message:
        error(message)

def setup():
    if not(len(sys.argv) > 2 and sys.argv[1] == '--setup' and sys.argv[2]):
        print("""{v}

This program requires a file {g}{file}{e} that has following configurations

    [main]
    texfile   = {g}TEX_FILE_PATH{e}
    remotedir = {g}REMOTE_DIR_PATH{e}

where TEX_FILE_PATH is the TeX file to be compiled,
and REMOTE_DIR_PATH (optional) is a path to a remote directory
to/from which the TeX files are transferred.

For automatic setup, please run {g}{this} --setup TEX_FILE_PATH{e}
""".format(
            v = product_name + " " + version,
            this = os.path.basename(sys.argv[0]),
            file = config_file,
            g = Color.g,
            e = Color.end))
        return

    tex = sys.argv[2]
    if not os.path.exists(tex):
        error('texfile "' + tex + '" not found.')
    if not tex.endswith('.tex'):
        error('TEX_FILE_PATH "' + tex + '" must have suffix ".tex".')
    tex = os.path.expanduser(tex)
    if os.path.isabs(tex):
        error('TEX_FILE_PATH "' + tex + '" should not be an absolute path')

    content = """[main]
texfile     = {tex}
# remotedir = ~/Dropbox/superproject/ (uncomment if you want)""".format(tex = tex)
    f = open(config_file, 'w')
    f.write(content)
    f.close()

    print("Setup completed.\nFor further configuration, edit {conf}.".format(conf = config_file))
    return



def read_config():
    iniparser = configparser.ConfigParser()
    iniparser.read(config_file)
    config = {}
    for i in ['texfile', 'remotedir']:
        config[i] = iniparser.get('main', i, fallback = None)

    if config['texfile']:
        if not os.path.exists(config['texfile']):
            error('main.texfile "' + config['texfile'] + '" not found.')
        if not config['texfile'].endswith('.tex'):
            error('main.texfile "' + config['texfile'] + '" must have suffix ".tex".')
        config['texfile'] = os.path.expanduser(config['texfile'])
        if os.path.isabs(config['texfile']):
            error('main.texfile "' + config['texfile'] + '" should not be an absolute path')

    if config['remotedir']:
        config['remotedir'] = os.path.expanduser(config['remotedir']).rstrip(os.path.sep)
        if not os.path.exists(config['remotedir']):
            warning('remotedir "' + config['remotedir'] + '" not found.')

    return config

def parse_args():
    argparser = argparse.ArgumentParser(add_help = False)
    argparser.error = lambda message: usage(message)
    argparser.add_argument("args", nargs = argparse.REMAINDER)
    argparser.add_argument("-h", "--help", action = 'store_true')
    argparser.add_argument("-V", action='version', version = product_name + " " + version)
    args = argparser.parse_args()
    if args.help:
        usage()
        sys.exit()
    return args.args



def check_latexmk():
    if not shutil.which(latexmk):
        error('latexmk not found.')
    pass

def get_tex_stem(texfile_path, basedir = ".", check_exists = True):
    """Returns *stem* of ``texfile_path``, asserting that it is with correct extension ``.tex``.
    If ``check_exists``, check that ``texfile_path``, relative to ``basedir``, exists."""

    # As we assume the configuration has already been validated, these are exceptions.
    if not texfile_path.endswith('.tex'):
        raise RuntimeError('texfile_path "{}" must have suffix ".tex"'.format(texfile_path))
    if check_exists and not os.path.exists(os.path.join(basedir or ".", texfile_path)):
        raise RuntimeError('specified texfile "{}" not found.'.format(texfile_path))
    return os.path.basename(texfile_path)[0:-4]

def check_absence(path):
    """Check that ``path`` does not exists. Error & Exit if exists.
    """
    if os.path.lexists(path):
        error('{} already exists.'.format(path))
    pass

def remove_file(path):
    """Remove the **file** if exists.
    """
    if os.path.exists(path):
        os.remove(path)
    pass

def get_dependencies(texfile_name, basedir = '.'):
    """Return files required to compile ``texfile_name``, excluding ``texfile_name`` itself."""
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
        error('Dependency cannot be resolved for {}.'.format(os.path.basename(texfile_name)))
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
    texfile_stem = get_tex_stem(texfile_path, basedir)

    print("\n\n" + Color.green("Compile " + texfile_path + " in " + Color.b + basedir + Color.g + "."))
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


def archive(src_tex_path, suffix, style = None):
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
    dst_tex_stem = get_tex_stem(src_tex_path) + suffix
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

    copy_with_mkdir(src_tex_path, dst_path("texfile"))
    dependents = get_dependencies(names["texfile"], names["tempdir"])
    for src in dependents:
        if os.path.isabs(f):
            warning('This TeX depends on {}, which is not archived. '.format(f))
            continue
        elif os.path.exists(src):
            dst = os.path.join(names["tempdir"], src)
            copy_with_mkdir(src, dst)
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


def push(texfile_path, remotedir_path, suffix = None):
    """Update the files in ``remotedir_path`` with the local version.
    ``.tex``, ``.bbl``, and ``.pdf`` files are updated as well as requisites."""

    compile(texfile_path, quiet = True)

    stem = get_tex_stem(texfile_path)
    dst_path = lambda src: os.path.join(remotedir_path, src)

    # tags: create, ignore, update
    file_list = [
            # TeX
            ('create', texfile_path, dst_path(os.path.join(os.path.dirname(texfile_path), stem + (suffix or "") + '.tex'))),
            # bbl
            ('create', stem + '.bbl', dst_path(stem + (suffix or "") + '.bbl')),
            # pdf
            ('create', stem + '.pdf', dst_path(stem + (suffix or "") + '.pdf')),
            ]
    for tag, src, dst in file_list:
        check_absence(dst)

    for src in get_dependencies(texfile_path):
        if os.path.isabs(src):
            # NOTE: should be warning? MISHO cannot imagine the case falling here.
            error('This TeX depends on {}, which cannot be pushed.'.format(src))
        dst = dst_path(src)
        if not os.path.exists(src):
            # FileNotFound should be treated by TeX compiler.
            # Just ignore such files.
            continue
        elif os.path.lexists(dst):
            if os.path.islink(dst):
                error('{} already exists as a symlink.'.format(dst))
            elif os.path.isdir(dst):
                error('{} already exists as a directory.'.format(dst))
            elif os.path.isfile(dst):
                delta = os.stat(src).st_mtime - os.stat(dst).st_mtime
                if abs(delta) < 2: # equivalent
                    file_list.append(('ignore', src, dst))
                elif delta > 0:    # newer local
                    file_list.append(('update', src, dst))
                else:              # newer remote
                    file_list.append(('conflict', src, dst))
            else:
                raise RuntimeError('{} cannot be identified.'.format(dst))
        else:
            file_list.append(('create', src, dst))

    push_and_pull_execute(file_list)
    return


def push_and_pull_execute(file_list):
    header = dict(
            create = Color.green('[create]'),
            update = Color.yellow('[update]'),
            conflict = Color.red('[conflict]'),
            ignore = '[ignore]')

    print("\nOperation:")
    [print('  ' + header[tag] + ' ' + dst) for tag, src, dst in file_list]

    if [x for x in file_list if x[0] == 'conflict']:
        error('Conflict detected. Abort for safety.')

    execute = [x for x in file_list if x[0] != 'ignore']
    if execute and input("\nCONTINUE? (y/N) ").lower() == 'y':
        src_len = max([len(src) for tag, src, dst in execute])
        fmt     = '{color}{src:<' + str(src_len) + '} => {dst}{e}'
        for tag, src, dst in file_list:
            if tag != 'ignore':
                copy_with_mkdir(src, dst)
                print(fmt.format(
                    src = src,
                    dst = dst,
                    color = Color.y if tag == 'update' else '',
                    e = Color.end))
    return


def pull(texfile_path, remotedir_path, suffix = None):
    """Update the local files with the version in ``remotedir_path`` without compile.
    Note that ``texfile_path`` is a path to the local version.
    ``.tex`` file is updated with suffix resolved.
    ``.bbl`` and ``.pdf`` files are kept.
    Requisites are updated."""

    stem = get_tex_stem(texfile_path, check_exists = False)
    remote_path = lambda src: os.path.join(remotedir_path, src)

    remote_texfile_path = remote_path(os.path.join(os.path.dirname(texfile_path), stem + (suffix or "") + '.tex'))
    if not os.path.isfile(remote_texfile_path):
        error('{} not found.'.format(remote_texfile_path))

    file_list = []
    if os.path.lexists(texfile_path):
        if os.path.islink(texfile_path) or not os.path.isfile(texfile_path):
            error('{} is not a file.'.format(texfile_path))
        delta = os.stat(texfile_path).st_mtime - os.stat(remote_texfile_path).st_mtime
        if abs(delta) < 2: # equivalent
            file_list.append(('ignore', remote_texfile_path, texfile_path))
        elif delta < 0:    # newer remote
            file_list.append(('update', remote_texfile_path, texfile_path))
        else:
            file_list.append(('conflict', remote_texfile_path, texfile_path))
    else:
        file_list.append(('create', remote_texfile_path, texfile_path))

    tempdir = tempfile.mkdtemp()
    temptex = shutil.copy2(remote_texfile_path, tempdir)
    dependents = get_dependencies(os.path.basename(temptex), tempdir)
    shutil.rmtree(tempdir)

    for dst in dependents:
        if os.path.isabs(dst):
            # NOTE: should be warning? MISHO cannot imagine the case falling here.
            error('This TeX depends on {}, which cannot be pushed.'.format(src))
        src = remote_path(dst)
        if not os.path.exists(src):
            # FileNotFound should be treated by TeX compiler.
            # Just ignore such files.
            continue
        elif os.path.lexists(dst):
            if os.path.islink(dst):
                error('{} already exists as a symlink.'.format(dst))
            elif os.path.isdir(dst):
                error('{} already exists as a directory.'.format(dst))
            elif os.path.isfile(dst):
                delta = os.stat(src).st_mtime - os.stat(dst).st_mtime
                if abs(delta) < 2: # equivalent
                    file_list.append(('ignore', src, dst))
                elif delta > 0:    # newer src=remote
                    file_list.append(('update', src, dst))
                else:              # newer dst=local
                    file_list.append(('conflict', src, dst))
                    flag_conflict = True
            else:
                raise RuntimeError('{} cannot be identified.'.format(dst))
        else:
            file_list.append(('create', src, dst))

    push_and_pull_execute(file_list)
    return



if __name__ == '__main__':
    config = read_config()

    if not config['texfile']:
        setup()
        sys.exit()

    args = parse_args()

    args_length = dict(
        compile = [1],
        archive = [2],
        JHEP    = [2],
        pull    = [1, 2],
        push    = [1, 2],
    )
    if len(args) == 0:
        usage('the following arguments are required: command')
    elif not(args[0] in args_length.keys()):
        usage('unknown command: ' + args[0])
    elif not(len(args) in args_length[args[0]]):
        usage('invalid options are specified for the command "' + args[0] + '"')

    args += [None]

    if args[0] == "compile":
        compile(config['texfile'])
    elif args[0] == "archive":
        archive(config['texfile'], args[1])
    elif args[0] == "JHEP":
        archive(config['texfile'], args[1], style = "JHEP")
    elif args[0] == "pull":
        pull(config['texfile'], config['remotedir'], suffix = args[1])
    elif args[0] == "push":
        push(config['texfile'], config['remotedir'], suffix = args[1])
