import typing as typ
import pyfuse3


class Auditor():
    def __init__(self) -> None:
        super().__init__()
        self.ops: typ.Optional[pyfuse3.Operations] = None
        self.read_forbidden_paths: typ.Set[str] = set()
        self.write_forbidden_paths: typ.Set[str] = set()

    @property
    def isactive(self):
        return True if self.ops is not None else False

    def notify_register(self, operation_instance) -> None:
        self.ops = operation_instance

    def notify_unregister(self) -> None:
        self.ops = None

    @staticmethod
    def _check_permission(forbidden_paths, given_path) -> bool:
        return not given_path.startswith(tuple(forbidden_paths))

    def readable(self, path) -> bool:
        return self._check_permission(self.read_forbidden_paths, path)

    def writable(self, path) -> bool:
        return self._check_permission(self.write_forbidden_paths, path)

    @staticmethod
    def _add_forbidden_path(forbidden_paths, given_path) -> None:
        return forbidden_paths.add(given_path)

    def add_read_forbidden_path(self, path) -> None:
        return self._add_forbidden_path(self.read_forbidden_paths, path)

    def add_write_forbidden_path(self, path) -> None:
        return self._add_forbidden_path(self.write_forbidden_paths, path)

    def request_handler(self, func_name, *args, **kwargs) -> bool:
        func = getattr(self, func_name)
        return func(*args, **kwargs)

    def getattr(self, vnode, ctx=None) -> None:
        print(vnode)
