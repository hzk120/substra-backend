from __future__ import absolute_import, unicode_literals

from substrapp.models import Objective
from substrapp.serializers.ledger.utils import create_ledger_asset


def createLedgerObjective(args, pkhash, sync=False):
    return create_ledger_asset(
        model=Objective,
        fcn='registerObjective',
        args=args,
        pkhash=pkhash,
        sync=sync)
