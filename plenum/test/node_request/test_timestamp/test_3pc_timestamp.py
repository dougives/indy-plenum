from collections import defaultdict

from plenum.common.constants import DOMAIN_LEDGER_ID, TXN_TIME
from plenum.test.instances.helper import recvd_prepares
from plenum.test.node_request.test_timestamp.helper import \
    get_timestamp_suspicion_count, make_clock_faulty
from plenum.test.spy_helpers import getAllReturnVals
from plenum.test.test_node import getNonPrimaryReplicas
from plenum.common.txn_util import get_txn_time

from plenum.test.helper import sdk_send_random_and_check


def test_replicas_prepare_time(looper, txnPoolNodeSet, sdk_pool_handle, sdk_wallet_client):
    # Check that each replica's PREPARE time is same as the PRE-PREPARE time
    sent_batches = 5
    for i in range(sent_batches):
        sdk_send_random_and_check(looper,
                                  txnPoolNodeSet,
                                  sdk_pool_handle,
                                  sdk_wallet_client,
                                  count=2)
        looper.runFor(1)

    for node in txnPoolNodeSet:
        for r in node.replicas:
            rec_prps = defaultdict(list)
            for p in recvd_prepares(r):
                rec_prps[(p.viewNo, p.ppSeqNo)].append(p)
            pp_coll = r.sentPrePrepares if r.isPrimary else r.prePrepares
            for key, pp in pp_coll.items():
                for p in rec_prps[key]:
                    assert pp.ppTime == p.ppTime

            # `last_accepted_pre_prepare_time` is the time of the last PRE-PREPARE
            assert r.last_accepted_pre_prepare_time == pp_coll.peekitem(-1)[
                1].ppTime

            # The ledger should store time for each txn and it should be same
            # as the time for that PRE-PREPARE
            if r.isMaster:
                for iv in node.txn_seq_range_to_3phase_key[DOMAIN_LEDGER_ID]:
                    three_pc_key = iv.data
                    for seq_no in range(iv.begin, iv.end):
                        assert get_txn_time(node.domainLedger.getBySeqNo(seq_no))\
                               == pp_coll[three_pc_key].ppTime


def test_non_primary_accepts_pre_prepare_time(looper, txnPoolNodeSet,
                                              sdk_wallet_client, sdk_pool_handle):
    """
    One of the non-primary has an in-correct clock so it thinks PRE-PREPARE
    has incorrect time
    """
    sdk_send_random_and_check(looper,
                              txnPoolNodeSet,
                              sdk_pool_handle,
                              sdk_wallet_client,
                              count=2)
    # send_reqs_to_nodes_and_verify_all_replies(looper, wallet1, client1, 2)
    # The replica having the bad clock
    confused_npr = getNonPrimaryReplicas(txnPoolNodeSet, 0)[-1]

    make_clock_faulty(confused_npr.node)

    old_acceptable_rvs = getAllReturnVals(
        confused_npr, confused_npr.is_pre_prepare_time_acceptable)
    old_susp_count = get_timestamp_suspicion_count(confused_npr.node)
    sdk_send_random_and_check(looper,
                              txnPoolNodeSet,
                              sdk_pool_handle,
                              sdk_wallet_client,
                              count=2)

    assert get_timestamp_suspicion_count(confused_npr.node) > old_susp_count

    new_acceptable_rvs = getAllReturnVals(
        confused_npr, confused_npr.is_pre_prepare_time_acceptable)

    # `is_pre_prepare_time_acceptable` first returned False then returned True
    assert [True, False, *old_acceptable_rvs] == new_acceptable_rvs
