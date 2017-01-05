#!env python3
# -*- coding: utf-8 -*-
# Time-Stamp: <2016-06-27 16:03:35>

product_name = 'RunTeX'
version      = '0.2.0'

latexmk      = 'latexmk'
config_file  = 'runtex.conf'

import os
import sys
import yaml
import shutil
import tempfile
import argparse
import subprocess
import filecmp



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

class cd:
    """
    Context manager for changing the current working directory.
    http://stackoverflow.com/questions/431684/how-do-i-cd-in-python
    """
    def __init__(self, newPath):
        self.newPath = os.path.expanduser(newPath)

    def __enter__(self):
        self.savedPath = os.getcwd()
        os.chdir(self.newPath)

    def __exit__(self, etype, value, traceback):
        os.chdir(self.savedPath)

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
    {this} compile (texfile)          compile texfile
    {this} archive (texfile) suffix   compile and create .tar.gz archive
    {this} JHEP (texfile) suffix      compile and create .tar.gz archive for JHEP
    {this} push (texfile) [suffix]    compile and copy relevant files to the remote directory
    {this} pull (texfile) [suffix]    pull files with <suffix> from the remote directory

<texfile> is mandatory if multiple rules are configured.
"""
    print(text.format(
        this = os.path.basename(sys.argv[0]),
    ))
    if message:
        error(message)


def setup():
    if not(len(sys.argv) > 2 and sys.argv[1] == '--setup' and sys.argv[2]):
        print("""{v}

This program requires a YAML file {g}{file}{e} that has following configurations

    ---
    texfile:   {g}TEX_FILE_PATH{e}
    remotedir: {g}REMOTE_DIR_PATH{e}

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

    content = """---
texfile:   {tex}
# remotedir: ~/Dropbox/superproject/ (uncomment if you want)
# extra:
#     - additional files to sync
#     -
""".format(tex = tex)
    f = open(config_file, 'w')
    f.write(content)
    f.close()

    print("Setup completed.\nFor further configuration, edit {conf}.".format(conf = config_file))
    return


def read_config():
    def check_config(config):
        if config.get('texfile'):
            if not os.path.exists(config['texfile']):
                error('config: texfile "' + config['texfile'] + '" not found.')
            if not config['texfile'].endswith('.tex'):
                error('config: texfile "' + config['texfile'] + '" must have suffix ".tex".')
            config['texfile'] = os.path.expanduser(config['texfile'])
            if os.path.isabs(config['texfile']):
                error('config: texfile "' + config['texfile'] + '" should not be an absolute path')
        if config.get('remotedir'):
            config['remotedir'] = os.path.expanduser(config['remotedir']).rstrip(os.path.sep)
            if not os.path.exists(config['remotedir']):
                warning('config: remotedir "' + config['remotedir'] + '" not found.')
        if config.get('texfile') is None and config.get('remotedir') is None:
            warning('config: phony rules without remotedir is useless')
        if config.get('extra') and not isinstance(config.get('extra'), list):
            error('config: extra must be a list.')

    configs = dict()
    try:
        with open(config_file, 'r') as f:
            for i in yaml.safe_load_all(f):
                if i is None:
                    continue
                if i.get("texfile") and i.get("name"):
                    error("a configuration has either of <texfile> or <name>")
                name = i.get("texfile") or i.get("name")
                if name is None:
                    error("a configuration needs <texfile> or <name>")
                else:
                    check_config(i)
                    configs[name] = i
    except FileNotFoundError:
        pass
    return configs


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

def get_tex_stem(texfile_path, check_exists = True):
    """Returns *stem* of ``texfile_path``, asserting that it is with correct extension ``.tex``.
    If ``check_exists``, check that it exists."""

    # As we assume the configuration has already been validated, these are exceptions.
    if not texfile_path.endswith('.tex'):
        raise RuntimeError('texfile_path "{}" must have suffix ".tex"'.format(texfile_path))
    if check_exists and not os.path.exists(texfile_path):
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

def pdf_from_eps(files):
    return [f for f in files
                if f.endswith('-eps-converted-to.pdf') and
                   f.replace('-eps-converted-to.pdf', '.eps') in files]

def get_dependencies(texfile_path):
    """Return files required to compile ``texfile_path``, excluding ``texfile_path`` itself."""
    print("\n\n" + Color.green("Check dependency of " + Color.b + texfile_path + Color.g + "."))

    output, stderr = subprocess.Popen(
            [latexmk, '-g', '-deps', '-bibtex-', '-interaction=nonstopmode', '-quiet', texfile_path],
            stdout = subprocess.PIPE).communicate()

    begin_tag = '#===Dependents for '
    end_tag   = '#===End dependents for '
    dep = output.decode("utf-8")
    dep = dep[dep.index(begin_tag) : ]
    dep = dep[0 : dep.rindex(end_tag)-1]
    # For begin_tag, exclude zero because it does exist at zero.
    if dep.rfind(begin_tag) > 0 or dep.find(end_tag) >= 0:
        error('Dependency cannot be resolved for {}.'.format(texfile_path))
    dep = dep.splitlines()[2:] # first two lines are removed

    dep = [x.lstrip("\n\r \t").rstrip("\n\r \t\\") for x in dep]
    # remove non-local files
    dep = list(set([os.path.normpath(x) for x in dep if x.find(os.path.sep + "texmf") == -1]))
    # remove TeX itself
    dep = [x for x in dep if x != texfile_path]
    # remove pdf converted from eps
    [dep.remove(f) for f in pdf_from_eps(dep)]
    # sort according to ext and then stem, and return.
    return sorted(dep, key = lambda x: os.path.splitext(x)[::-1])

def get_and_collect_dependencies(orig_texfile_path, target_dir, new_texfile_path):
    """
    Return files required to compile ``orig_texfile_path`` (relative path from ``cwd``),
    but the TeX file is copied to ``target_dir``/``new_texfile_path``
    and files required to compile are collected to ``target_dir``.
    """
    copy_with_mkdir(orig_texfile_path, os.path.join(target_dir, new_texfile_path))
    for trial in range(0, 5):
        with cd(target_dir):
            deps = get_dependencies(new_texfile_path)
            deps_to_copy = [f for f in deps if not os.path.exists(f)]
        retry = False
        for f in deps_to_copy:
            if os.path.isabs(f):
                warning('This TeX depends on {}, which is not archived. '.format(f))
            elif os.path.exists(f):
                copy_with_mkdir(f, os.path.join(target_dir, f))
                retry = True
            else:
                warning('Required file {} not found.'.format(f))
        if not retry:
            return deps
    error('Dependency not solved.')

def compare_files_and_get_mode(src, dst):
    """Compare files, assuming ``src`` and ``dst`` are existing files."""
    if filecmp.cmp(src, dst):
        return 'ignore'
    elif os.stat(src).st_mtime > os.stat(dst).st_mtime:
        return 'update'
    else:
        return 'conflict'


# 'path' means full-path from a base (usually the currrent) directory to the file/dir.
# 'stem' is a basename of file, with no dir, and no "extension".
# 'name' is a basename of file including extension, and possibly with dir.

def compile(config, remove_misc = False, quiet = False):
    check_latexmk()
    texfile_path = config["texfile"]
    texfile_stem = get_tex_stem(texfile_path)

    cwd = os.getcwd()
    print("\n\n" + Color.green("Compile " + texfile_path+ " in " + Color.b + cwd + Color.g + "."))
    subprocess.Popen([latexmk, '-pdf', '-quiet' if quiet else '', texfile_path]).communicate()

    if remove_misc:
        print("\n\n" + Color.green("Unnecessary files in " + Color.b + cwd + Color.g + " are removed."))
        tempdir  = tempfile.mkdtemp()
        shelters = {}
        # pdf and bbl are created in current dirrectory.
        for ext in [".pdf", "bbl"]:
            src = os.path.join(texfile_stem + ext)
            dst = os.path.join(tempdir, src)
            if os.path.exists(src):
                shelters[src] = dst
        for src in shelters.keys():
            shutil.move(src, tempdir)
        subprocess.Popen([latexmk, '-CA', texfile_path]).communicate()
        for dst in shelters.values():
            shutil.move(dst, '.')
        os.rmdir(tempdir)


def archive(config, suffix, style = None):
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
    src_tex_path = config["texfile"]
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

    deps = get_and_collect_dependencies(src_tex_path, names["tempdir"], names["texfile"])

    with cd(names["tempdir"]):
        compile(names["texfile"], remove_misc = True, quiet = True)
        [remove_file(f.replace('.eps', '-eps-converted-to.pdf')) for f in deps if f.endswith('.eps')]

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


def push(config, suffix = None):
    """Update the files in ``remotedir_path`` with the local version.
    ``.tex``, ``.bbl``, and ``.pdf`` files are updated as well as requisites."""

    texfile_path   = config.get("texfile")
    remotedir_path = config["remotedir"]

    compile(texfile_path, quiet = True)

    stem = get_tex_stem(texfile_path)
    dst_path = lambda src: os.path.join(remotedir_path, src)

    files = [ # src, dst
        (texfile_path, dst_path(os.path.join(os.path.dirname(texfile_path), stem + (suffix or "") + '.tex'))),
        (stem + '.bbl', dst_path(stem + (suffix or "") + '.bbl')),
        (stem + '.pdf', dst_path(stem + (suffix or "") + '.pdf'))]

    # tags: create, ignore, update
    file_list = []
    for src, dst in files:
        if not os.path.isfile(src):
            warning('{} not found.'.format(src))
            continue
        if os.path.islink(dst):
            error('{} already exists as a symlink.'.format(dst))
        elif os.path.isdir(dst):
            error('{} already exists as a directory.'.format(dst))
        elif os.path.lexists(dst):
            tag = 'update'
        else:
            tag = 'create'
        file_list.append((tag, src, dst))
    existing_files = [dst for tag, src, dst in file_list if tag == 'update']
    if existing_files:
        print(Color.yellow('The following files exist.'))
        [print(dst) for dst in existing_files]
        if input(Color.yellow("\nFORCE OVERWRITE? (y/N) ")).lower() != 'y':
            error('Abort.')

    for src in get_dependencies(texfile_path):
        if os.path.isabs(src):
            # NOTE: should be warning? MISHO cannot imagine the case falling here.
            error('This TeX depends on {}, which cannot be pushed.'.format(src))
        dst = dst_path(src)
        mode = ''
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
                mode = compare_files_and_get_mode(src, dst)
            else:
                raise RuntimeError('{} cannot be identified.'.format(dst))
        else:
            mode = 'create'
        file_list.append((mode, src, dst))

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


def pull(config, suffix = None):
    """Update the local files with the version in ``remotedir_path`` without compile.
    Note that ``texfile_path`` is a path to the local version.
    ``.tex`` file is updated with suffix resolved.
    ``.bbl`` and ``.pdf`` files are kept.
    Requisites are updated."""

    texfile_path   = config.get("texfile")
    remotedir_path = config["remotedir"]
    stem = get_tex_stem(texfile_path, check_exists = False)
    remote_path = lambda src: os.path.join(remotedir_path, src)

    texfile_path_remote = os.path.join(os.path.dirname(texfile_path), stem + (suffix or "") + '.tex')
    remote_tex          = remote_path(texfile_path_remote)
    if not os.path.isfile(remote_tex):
        d = os.path.dirname(remote_tex)
        candidates = "\t".join([f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)) and f.startswith(stem) and f.endswith('.tex') ])
        error('{tex} not found.\n\nCandidates are:\n{candidates}'.format(
            tex = remote_tex,
            candidates = candidates,
            ))

    file_list = []
    mode = ''
    if os.path.lexists(texfile_path):
        if os.path.islink(texfile_path) or not os.path.isfile(texfile_path):
            error('{} is not a file.'.format(texfile_path))
        mode = compare_files_and_get_mode(remote_tex, texfile_path)
    else:
        mode = 'create'
    file_list.append((mode, remote_tex, texfile_path))

    tempdir = tempfile.mkdtemp()
    with cd(remotedir_path):
        dependents = get_and_collect_dependencies(texfile_path_remote, tempdir, texfile_path)
    shutil.rmtree(tempdir)

    for dst in dependents:
        if os.path.isabs(dst):
            # NOTE: should be warning? MISHO cannot imagine the case falling here.
            error('This TeX depends on {}, which cannot be pushed.'.format(src))
        src = remote_path(dst)
        mode = ''
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
                mode = compare_files_and_get_mode(src, dst)
            else:
                raise RuntimeError('{} cannot be identified.'.format(dst))
        else:
            mode = 'create'
        file_list.append((mode, src, dst))

    push_and_pull_execute(file_list)
    return



if __name__ == '__main__':
    config_list = read_config()

    if len(config_list) == 0:
        setup()
        sys.exit()

    args_length_dict = dict(
        compile = [0],
        archive = [1],
        JHEP    = [1],
        pull    = [0, 1],
        push    = [0, 1],
    )

    args = parse_args()
    if len(args) == 0:
        usage('arguments are missing')

    command = args.pop(0)
    target = args.pop(0) if (len(args) > 0 and args[0] in config_list.keys()) else None

    args_length = args_length_dict.get(command)
    if args_length is None:
        usage('unknown command: ' + command)
    if not(len(args) in args_length):
        usage('invalid options are specified for the command "' + command + '"' + \
              ("\n(maybe wrong <texfile> is specified?)" if (len(args) - 1 in args_length and target is None) else ""))

    if target is None:
        if len(config_list) == 1:
            target = config_list.keys()[0]
        else:
            usage('<texfile> is missing')

    config = config_list[target]

    def needs(item):
        if config.get(item) is None:
            error('command "' + command + '" is invalid without "' + item + '" in configuration.')

    if command == "compile":
        needs('texfile')
        compile(config)
    elif command == "archive":
        needs('texfile')
        archive(config, args[0])
    elif command == "JHEP":
        needs('texfile')
        archive(config, args[0], style = "JHEP")
    if command == "pull":
        needs('remotedir')
        pull(config, suffix = (args[0] if len(args) == 1 else None))
    elif command == "push":
        needs('remotedir')
        push(config, suffix = (args[0] if len(args) == 1 else None))
