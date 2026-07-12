# P3 fixed-seed placebo tradability / termination source package

## 結論

- Core input blockers：11 episodes。
- 官方同日雙邊交易價可解：11 episodes。
- 仍需終止交易／holder-treatment證據：0 episodes。
- 本包只用 exact official dates；未使用最後價、鄰日、benchmark或current status回填。
- ready_for_core_p3_phase_b_placebo_tradability_patch_absorption=true。
- future_data_violation_count=0。

## 6470修正

6470在2023-07-21後仍有TPEx官方成交資料，因此原本的termination推論是compact漏列造成的false positive，不建立虛構forced-exit事件。

## 下一棒

交 Core/Data absorption/rechain；不直接交 Experiments。
