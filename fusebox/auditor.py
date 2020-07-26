import typing as typ
import pyfuse3
import enum


class SecurityModel(enum.Enum):
    WHITELIST = enum.auto()
    BLACKLIST = enum.auto()


class Auditor():
    def __init__(self) -> None:
        super().__init__()
        self.ops: typ.Optional[pyfuse3.Operations] = None
        self.permission_read_paths: typ.List[str] = list()
        self.permission_write_paths: typ.List[str] = list()
        self.security_model = SecurityModel.WHITELIST

    @property
    def isactive(self):
        return True if self.ops is not None else False

    def notify_register(self, operation_instance) -> None:
        self.ops = operation_instance

    def notify_unregister(self) -> None:
        self.ops = None

    def _check_permission(self, forbidden_paths, given_path) -> bool:
        if self.security_model == SecurityModel.BLACKLIST:
            return not given_path.startswith(tuple(forbidden_paths))
        elif self.security_model == SecurityModel.WHITELIST:
            return given_path.startswith(tuple(forbidden_paths))
        else:
            raise RuntimeError

    def ask_readable(self, path) -> bool:
        return self._check_permission(self.permission_read_paths, path)

    def ask_writable(self, path) -> bool:
        return self._check_permission(self.permission_write_paths, path)
