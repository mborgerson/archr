import subprocess
import contextlib
import tempfile
import tarfile
import logging
import glob
import os
import io
import re

l = logging.getLogger("archr.targets")

from abc import ABC
from abc import abstractmethod


class Target(ABC):
    """
    An autom defines a packetized unit of vulnerable software
    """

    #
    # Abstract methods
    #

    def __init__(
        self,
        target_args=None, target_path=None, target_env=None, target_cwd=None, target_os='linux', target_arch='x86_64',
        ip_version=4
    ):
        """
        Create an autom

        Should provide:
        - The base metadata (architecture, version, .... ..)
        - The image, if needed, or Dockerfile/Vagrant....

        Produces a target ready to run build()
        :param args:
        :param kwargs:
        """
        if target_os == 'cgc':
            target_arch = 'i386'
        self.target_args = target_args
        self.target_path = target_path
        self.target_env = target_env
        self.target_cwd = target_cwd
        self.target_os = target_os
        self.target_arch = target_arch
        self._local_path = None
        self.target_args_prefix = [ ]
        self.ip_version = ip_version

        self.tmp_bind = None  # the /tmp in the target is mapped to `tmp_bind` on the host. currently only used in
                              # DockerTarget. it impacts how resolve_local_path() works.

    @abstractmethod
    def mount_local(self, where=None):
        """
        Mounts the target on the local filesystem.

        :param str where: the path to mount it to
        """
        pass

    def build(self):
        """
        Some automs require a "build" step.  For example, Vagrant/Docker/Ansible will need to run for some targets
        This step should begin with the metadata passed to the constructor, and produce a state ready for run()
        :return:
        """
        if not any(e.startswith("PWD=") for e in self.target_env):
            self.target_env.append("PWD=%s"%self.target_cwd)
        if "LD_BIND_NOW=1" not in self.target_env:
            self.target_env.append("LD_BIND_NOW=1")
        return self

    @abstractmethod
    def remove(self):
        """
        The opposite of build().
        :return:
        """
        pass

    @abstractmethod
    def start(self):
        """
        Start the target.
        :return:
        """
        pass

    def stop(self):
        """
        Start the target.
        :return:
        """
        pass

    @abstractmethod
    def restart(self):
        """
        Restart the target.
        :return:
        """
        pass

    @abstractmethod
    def _run_command(self, args, env, **kwargs):
        """
        Run a command inside the target.
        :return:
        """
        pass

    @abstractmethod
    def inject_tarball(self, target_path, tarball_path=None, tarball_contents=None):
        """
        Extracts a tarball into the target.

        :param str target_path: The path to extract to.
        :param str tarball_path: The path to the tarball.
        :param str tarball_contents: Alternatively, the content of the tarball.
        """
        pass

    @abstractmethod
    def retrieve_tarball(self, target_path):
        """
        Retrieves files from the target in the form of tarball contents.

        :param str target_path: The path to retrieve.
        """
        pass

    @property
    @abstractmethod
    def ipv4_address(self):
        """
        The ipv4 address that this target receives traffic on.
        """
        pass

    @property
    @abstractmethod
    def ipv6_address(self):
        """
        The ipv6 address that this target receives traffic on.
        """
        pass

    @property
    @abstractmethod
    def tcp_ports(self):
        """
        The TCP ports that this target listens on.
        """
        pass

    @property
    @abstractmethod
    def udp_ports(self):
        """
        The UDP ports that this target listens on.
        """
        pass

    @property
    @abstractmethod
    def tmpwd(self):
        """
        Temporary working directory in the target.
        """
        pass

    #
    # Convenience methods
    #

    def __enter__(self): return self
    def __exit__(self, *args): self.stop()

    @property
    def local_path(self):
        """
        The local mounted path on the host.
        """
        if self._local_path is None:
            raise ArchrError("target.mount_local() must be run before target.local_path can be accessed.")
        return self._local_path

    @property
    def main_binary_args(self):
        """
        Return the args that will be passed to the main binary.
        """
        exe = self.target_args[0]
        if re.match(r"ld[0-9A-Za-z\-]*\.so.*", os.path.basename(exe)) is not None:
            args = self.target_args[1:]
            if args[0] == "--library-path":
                args = args[2:]
            return args
        return self.target_args

    def resolve_local_path(self, target_path):
        """
        The local equivalent of target_path on the host.
        :returns str: the local path
        """

        def _chroot_path(path, root):
            """
            Make sure the final path always starts with @root. No escape is allowed.
            """
            realpath = os.path.realpath(path)
            if not realpath.startswith(root):
                realpath = os.path.join(root, realpath.lstrip(os.path.sep))
            return realpath

        if not target_path.startswith("/"):
            l.warning("Non-absolute path resolution is hit and miss, depending on context. Be careful.")

        if self.tmp_bind and target_path.startswith("/tmp"):
            # Handle tmp_bind
            target_path = os.path.join(self.tmp_bind, target_path[4:].lstrip(os.path.sep))
            realpath = _chroot_path(target_path, self.tmp_bind)
            return realpath

        if not target_path.startswith(self.local_path):
            target_path = os.path.join(self.local_path, target_path.lstrip(os.path.sep))
        realpath = _chroot_path(target_path, self.local_path)
        return realpath

    def resolve_glob(self, target_glob):
        """
        Should resolve a glob on the target.
        WARNING: THE DEFAULT IMPLEMENTATION OF THIS IS INSECURE OUT OF LAZINESS AND WILL FAIL WITH SPACES IN FILES OR MULTIPLE FILES

        :param string target_glob: the glob
        :returns list: a list of the resulting paths (as strings)
        """
        try:
            local_glob = glob.glob(self.resolve_local_path(target_glob))
            # note that resolved globs may not start with self.local_path. they can start with self.tmp_bind as well.
            fixed_paths = [ ]
            local_path_prefix = self.local_path
            tmp_bind_prefix = self.tmp_bind if self.tmp_bind else None
            for g in local_glob:
                # we assume self.tmp_bind is never a prefix of self.local_path.
                # otherwise the elif case will never be satisfied.
                if tmp_bind_prefix and g.startswith(tmp_bind_prefix):
                    fixed_paths.append(os.path.join("/tmp",
                        g[len(tmp_bind_prefix.rstrip(os.path.sep)):].lstrip("/")))
                elif g.startswith(local_path_prefix):
                    fixed_paths.append(g[len(local_path_prefix.rstrip(os.path.sep)):])
                else:
                    raise ValueError("Unexpected resolved local path %s. "
                                     "It should start with either local_path or tmp_bind." % g)
            return fixed_paths
        except ArchrError:
            stdout,_ = self.run_command(["/bin/sh", "-c", "ls -d "+target_glob]).communicate()
            paths = [ p.decode('utf-8') for p in stdout.split() ]
            return paths

    @abstractmethod
    def get_proc_pid(self, proc):
        """
        :param proc: Process name
        :return: Process pid
        """
        pass

    def inject_path(self, src, dst=None):
        """
        Injects a file or directory into the target.

        :param str src: the source path (on the host)
        :param str dst: the dst path (on the target)
        """
        self.inject_paths({dst: src})

    def inject_paths(self, files):
        """
        Inject different files or directories into the target.

        :param dict files: A dict of { dst_path: src_path }
        :return:
        """
        with io.BytesIO() as f:
            t = tarfile.open(fileobj=f, mode='w')
            for dst,src in files.items():
                t.add(src, arcname=dst)
            t.close()
            f.seek(0)
            self.inject_tarball("/", tarball_contents=f.read())

    def inject_contents(self, files, modes=None):
        """
        Injects files or into the target.

        :param dict files: A dict of { dst_path: byte_contents }
        :param dict modes: An optional dict of { dst_path: permissions }
        """
        with io.BytesIO() as f:
            with tarfile.open(fileobj=f, mode='w') as t:
                for dst,content in files.items():
                    i = tarfile.TarInfo(name=dst)
                    i.size = len(content)
                    i.mode = 0o777
                    if modes and dst in modes:
                        i.mode = modes[dst]
                    t.addfile(i, fileobj=io.BytesIO(content))
            f.seek(0)
            self.inject_tarball("/", tarball_contents=f.read())

    def retrieve_into(self, target_path, local_path):
        """
        Retrieves a path on the target into a path locally.

        :param str target_path: The path to retrieve.
        :param str local_path: The path to put it locally.
        """
        with io.BytesIO() as f:
            f.write(self.retrieve_tarball(target_path))
            f.seek(0)
            with tarfile.open(fileobj=f, mode='r') as t:
                to_extract = [ m for m in t.getmembers() if m.path.startswith(os.path.basename(target_path).lstrip("/")) ]
                if not to_extract:
                    raise FileNotFoundError("%s not found on target" % target_path)

                #local_extract_dir = os.path.join(local_path, os.path.dirname(target_path).lstrip("/"))
                #with contextlib.suppress(FileExistsError):
                #   os.makedirs(local_extract_dir)
                #assert os.path.exists(local_extract_dir)

                with contextlib.suppress(FileExistsError):
                    os.makedirs(local_path)
                t.extractall(local_path, members=to_extract)

    def retrieve_contents(self, target_path):
        """
        Retrieves the contents of a file from the target.

        :param str target_path: The path to retrieve.
        :returns bytes: the contents of the file
        """
        with io.BytesIO() as f:
            f.write(self.retrieve_tarball(target_path))
            f.seek(0)
            with tarfile.open(fileobj=f, mode='r') as t:
                with t.extractfile(os.path.basename(target_path)) as fp:
                    return fp.read()

    def retrieve_glob(self, target_glob):
        """
        Retrieves a globbed path on the target.

        :param str target_path: The path to retrieve.
        """
        paths = self.resolve_glob(target_glob)
        if len(paths) == 0:
            raise FileNotFoundError("no match for glob in retrieve_glob")
        if len(paths) != 1:
            raise ValueError("retrieve_glob requires a single glob match")
        return self.retrieve_contents(paths[0])

    @contextlib.contextmanager
    def retrieval_context(self, target_path, local_thing=None, glob=False): #pylint:disable=redefined-outer-name
        """
        This is a context manager that retrieves a file from the target upon exiting.

        :param str target_path: the path on the target to retrieve
        :param local_thing: Can be a file path (str) or a write()able object (where the file will be written upon retrieval), or None, in which case a temporary file will be yielded.
        :param glob: Whether to glob the target_path.
        """

        with contextlib.ExitStack() as stack:
            if type(local_thing) in (str, bytes):
                to_yield = local_thing
                local_file = stack.enter_context(open(local_thing, "wb"))
            elif local_thing is None:
                to_yield = tempfile.mktemp()
                local_file = stack.enter_context(open(to_yield, "wb"))
            elif hasattr(local_thing, "write"):
                to_yield = local_thing
                local_file = local_thing
            else:
                raise ValueError("local_thing argument to retrieval_context() must be a str, a write()able object, or None")

            try:
                yield to_yield
            finally:
                local_file.write(self.retrieve_glob(target_path) if glob else self.retrieve_contents(target_path))

    @contextlib.contextmanager
    def replacement_context(self, target_path, temp_contents, saved_contents=None):
        """
        Provides a context within which a file on the target is overwritten with different contents.
        Will yield the old contents.

        :param str target_path: the path on the target
        :param bytes temp_contents: the contents to overwrite the target with
        :param bytes saved_contents: the original contents of the file, to avoid needlessly retrieving it
        """
        saved_contents = saved_contents if saved_contents is not None else self.retrieve_contents(target_path)
        self.inject_contents({target_path: temp_contents})
        try:
            yield saved_contents
        finally:
            self.inject_contents({target_path: saved_contents})

    @contextlib.contextmanager
    def run_context(self, *args, timeout=10, **kwargs):
        """
        A context around run_command. Yields a subprocess.
        """

        p = self.run_command(*args, **kwargs)
        try:
            yield p
            p.stdin.close()
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.restart()
            raise
        finally:
            # TODO: probably insufficient
            p.terminate()

    def flight(self, *args, result=None, **kwargs):
        return Flight(self, self.run_command(*args, **kwargs), result=result)

    @contextlib.contextmanager
    def flight_context(self, *args, timeout=1, **kwargs):
        flight = self.flight(*args, **kwargs)
        try:
            yield flight
        finally:
            flight.stop(timeout=timeout)

    @contextlib.contextmanager
    def shellcode_context(self, *args, asm_code=None, bin_code=None, **kwargs):
        """
        A context that runs the target with shellcode injected over the entrypoint.
        Useful for operating in the normal process context of the target.

        :param *args: args to pass to run_context()
        :param **kwargs: kwargs to pass to run_context()
        :param str asm_code: assembly to assemble into shellcode
        :param bytes bin_code: binary code to inject directly
        """

        original_binary = self.retrieve_contents(self.target_path)
        hooked_binary = hook_entry(original_binary, asm_code=asm_code, bin_code=bin_code)
        with self.replacement_context(self.target_path, hooked_binary, saved_contents=original_binary):
            with self.run_context(*args, **kwargs) as p:
                yield p

    def run_command(
        self, args=None, args_prefix=None, args_suffix=None, env=None, # for us
        **kwargs # for subclasses
    ):
        """
        Run a command inside the target.
        :return: A subprocess
        """
        command_args = args or (self.target_args_prefix + self.target_args)

        if args_prefix:
            command_args = args_prefix + command_args
        if args_suffix:
            command_args = command_args + args_suffix

        l.debug("Running command: '%s'", "' '".join(command_args))
        return self._run_command(command_args, self.target_env if env is None else env, **kwargs)


from .docker_target import DockerImageTarget
from .local_target import LocalTarget
from ..utils import hook_entry
from ..errors import ArchrError
from .flight import Flight
