from agent.marketplace_port import get_marketplace

def test_submit_is_exactly_once():
    m = get_marketplace()
    d = m.create_proposal_draft("a01", "hi", idem_key="k1")
    a = m.submit_proposal(d.id, idem_key="k2")
    b = m.submit_proposal(d.id, idem_key="k2")
    assert a.ok and b.replayed and m.get_connects_balance() == 100 - a.connects_cost

def test_dry_run_has_no_side_effects():
    m = get_marketplace()
    d = m.create_proposal_draft("a01", "hi", idem_key="k1")
    r = m.submit_proposal(d.id, idem_key="k3", dry_run=True)
    assert r.dry_run and r.connects_cost > 0 and m.get_connects_balance() == 100
