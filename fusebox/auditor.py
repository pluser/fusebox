import typing as typ
from collections import namedtuple
import pyfuse3
import enum


class SecurityModel(enum.Enum):
    WHITELIST = enum.auto()
    BLACKLIST = enum.auto()


class Order(enum.Enum):
    ALLOW = enum.auto()
    DENY = enum.auto()


Permission = namedtuple('Permission', 'order path')


class Auditor():
    def __init__(self) -> None:
        super().__init__()
        self.ops: typ.Optional[pyfuse3.Operations] = None
        self.permission_read: typ.List[Permission] = list()
        self.permission_write: typ.List[Permission] = list()
        self.security_model = SecurityModel.WHITELIST

    def _get_order(self, permission_list: typ.List[Permission], target_path) -> typ.Optional[Order]:
        perms = reversed(permission_list)
        for l in perms:
            if target_path.startswith(l.path):
                return l.order
        return None  # If no valid order found

    def _check_permission(self, permission_list: typ.List[Permission], given_path: str) -> bool:
        order = self._get_order(permission_list, given_path)
        if order:
            if order == Order.ALLOW:
                return True
            elif order == Order.DENY:
                return False
            else:
                raise RuntimeError
        else:
            if self.security_model == SecurityModel.BLACKLIST:
                return True
            elif self.security_model == SecurityModel.WHITELIST:
                return False
            else:
                raise RuntimeError

    def ask_readable(self, path: str) -> bool:
        return self._check_permission(self.permission_read, path)

    def ask_writable(self, path: str) -> bool:
        return self._check_permission(self.permission_write, path)

    def allowread(self, path: str) -> None:
        self.permission_read.append(Permission(Order.ALLOW, path))

    def allowwrite(self, path: str) -> None:
        self.permission_write.append(Permission(Order.ALLOW, path))

    def denyread(self, path: str) -> None:
        self.permission_read.append(Permission(Order.DENY, path))

    def denywrite(self, path: str) -> None:
        self.permission_write.append(Permission(Order.DENY, path))
