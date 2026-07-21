from . import models
from . import wizard


def post_init_hook(env):
    env["cr.payroll.native.setup"].sudo().setup_native_payroll()
