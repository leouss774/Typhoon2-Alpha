"""Statuts canoniques : les quatre situations ne sont jamais confondues."""
from risk_engine.canonical import (CanonicalVariable, Domain, Scope, Status,
                                   TimeHorizon, VariableBag)
from risk_engine.collector_hardening import classify_source


def test_source_error_is_not_no_feature_found():
    assert classify_source(None, error_message="404") is Status.SOURCE_ERROR
    assert classify_source({"results": 0}) is Status.NO_FEATURE_FOUND
    assert classify_source(None, configured=False) is Status.NOT_CONFIGURED
    assert classify_source(None, requested=False) is Status.NOT_COLLECTED
    assert Status.SOURCE_ERROR is not Status.NO_FEATURE_FOUND


def test_default_value_forced_and_unusable():
    v = CanonicalVariable(key="k", value="A1", is_default=True, status=Status.AVAILABLE)
    assert v.status is Status.DEFAULT_VALUE
    assert not v.usable
    assert v.quality == 0.0


def test_prospective_horizon_never_usable():
    v = CanonicalVariable(key="k", value=1, status=Status.AVAILABLE,
                          time_horizon=TimeHorizon.PROSPECTIVE)
    assert not v.usable


def test_hierarchy_lower_rank_never_overwrites_higher():
    bag = VariableBag()
    good = CanonicalVariable(key="k", value="officiel", status=Status.AVAILABLE,
                             source="georisques", source_rank=1, domain=Domain.HAZARD)
    weak = CanonicalVariable(key="k", value="declare", status=Status.AVAILABLE,
                             source="questionnaire", source_rank=3, domain=Domain.HAZARD)
    bag.add(good)
    bag.add(weak)
    assert bag.get("k").value == "officiel"
    assert bag.get("k").superseded[0]["value"] == "declare"


def test_conflict_recorded_and_both_values_kept():
    bag = VariableBag()
    bag.add(CanonicalVariable(key="k", value="A", status=Status.AVAILABLE, source="bdnb",
                              source_rank=4))
    bag.add(CanonicalVariable(key="k", value="B", status=Status.AVAILABLE,
                              source="questionnaire", source_rank=2))
    assert len(bag.conflicts) == 1
    assert bag.get("k").value == "B"
    assert any(s["value"] == "A" for s in bag.get("k").superseded)


def test_no_conflict_when_values_agree():
    bag = VariableBag()
    for rank, src in ((4, "bdnb"), (2, "user")):
        bag.add(CanonicalVariable(key="k", value="same", status=Status.AVAILABLE,
                                  source=src, source_rank=rank))
    assert bag.conflicts == []
