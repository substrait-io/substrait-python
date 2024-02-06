# SPDX-License-Identifier: Apache-2.0


from substrait.planloader import planloader


def test_main():
    print(planloader.__file__)
    print(dir(planloader))
    testplan = planloader.load_substrait_plan('tests/tpch-plan01.json')
    planloader.save_substrait_plan(testplan, 'myoutfile.splan', planloader.PlanFileFormat.TEXT.value)
