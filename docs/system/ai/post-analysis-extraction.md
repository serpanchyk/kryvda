# Inference v4

Production analysis is target monitoring. A Post Revision is eligible only when a Unicode-aware,
case-insensitive match finds an approved alias of a monitored registry entity. Exact matches use
letter/digit boundaries. A conservative deterministic Ukrainian/Russian nominal-inflection
matcher also recognizes grammatical forms token by token. A bare inflected surname from a person
alias is accepted only when it uniquely identifies one monitored registry entity; it does not
perform fuzzy matching. Feminine adjective cases (`Європейської Солідарності`) and `-ість` nouns
are recognized. A state-body alias whose every occurrence names a foreign institution
(`Міноборони рф`, `МЗС КНР`, `російський Генштаб`) does not admit the Ukrainian entity, and a Pass 1
mention that only ever occurs in such a context stays an unresolved post-local actor. No alias has
a case-sensitive or entity-specific rule: an alias that is also a common word (`Голос`, `ЧЕСНО`)
admits the post, and Pass 1 decides whether the match names the registry actor.

The AI worker makes five semantic model calls:

1. `candidates` receives every registry candidate matched by alias (`r*` ID, canonical name, type,
   exact matched forms and the sentences around them) and answers, per candidate, a short
   `reason` and `same_actor`. Its guided-generation schema names every candidate ID as a
   required property, so no decision can be skipped or invented.
2. `entities` groups exact textual references to relevant identifiable actors (the v3.6 prompt).
3. `claims` extracts atomic claims involving at least one monitored entity, with attribution,
   Ukrainian epistemic status, and one exact evidence string. `presentation` is deliberately not
   stored or inferred.
4. `targets` receives, per claim, every actor named in it (monitored or not) plus «інший актор
   або ніхто з переліку» and answers, per claim, a short `reason` and the names of every actor the
   claim source evaluates. The guided schema limits each claim to its own actor names. Pairs whose
   target is not named become `відсутнє` without Pass 3; if the pass stays invalid every pair is
   classified (`classify_all_pairs`).
5. `classification` classifies every remaining monitored claim-target pair for Ukrainian stance
   and up to two attack-rhetoric categories.

Between calls, backend code validates grounding, resolves approved aliases including inflected
forms, assigns `e*` and `c*` IDs, records candidates, and derives deterministic evidence offsets.
Before Pass 1 validation it removes repeated strings and ungrounded strings, retaining each entity
group that still has at least one exact mention and keeps a mention repeated across groups only
in its first group. Only confirmed candidates become monitored entities, with every exact surface
form that caused the match; a rejected candidate cannot re-enter through a Pass 1 group. When no
monitored entity remains, Pass 2 and Pass 3 are skipped and the run completes without claims. If
the candidate pass stays invalid after repair, every candidate is admitted
(`admit_all_candidates`); if Pass 1 stays invalid, the confirmed candidates alone continue
(`prefilter_entities_only`). The decision was first folded into Pass 1, but Mamay then wrongly
rejected real entities (often the first candidate) whether asked for a yes/no per candidate or for
a rejection list. With the separate call and sentence context Mamay confirmed 346 of 349
candidates on the 100 reviewed examples and rejected the adverb `Чесно` and `Чесна мобілізація`;
its one wrong rejection read «актор» as a profession, so the prompt now says person, body or
organization. A Pass 1 response that
breaks (Mamay can loop on a repeated name) is salvaged before repair: every complete entity group
is kept when it validates, because the repair request carries neither the post nor the candidates.
A mention repeated inside one group is harmless. Mixed Pass 1 groups are
partitioned by uniquely resolvable mention, leaving ambiguous text as a post-local candidate. Pass
2 receives the whole post. Its deterministic sanitizer drops only invalid or non-monitored claims,
deduplicates retained claims, and realigns uniquely recoverable quote/dash/whitespace evidence to
the exact source substring. `claims: []` is valid. Pass 3 receives the normalized claim, exact
evidence, the evidence sentences with one neighboring sentence on each side, the claim's
responsible source (`claim_source`: `канал`, `неназване джерело` or the actor's name) and
`source_is_target`, so a target's self-presentation is never read as another source's evaluation.

Schemas live in `monitoring_common/contracts/schemas/inference_v3_*`. Prompts are Ukrainian and
technical JSON keys remain English. IDs, canonical resolution, offsets, candidates, persistence,
and retry bookkeeping are deterministic backend responsibilities. Pass 3 splits stable expected
pairs into bounded requests (default five). After a whole-document parse failure it salvages only
complete classification objects, retries still-missing pairs in bounded batches, then retries each
remaining pair individually. A non-negative stance with returned rhetoric is sanitized to an empty
rhetoric list without changing the stance, so that invariant violation does not cause pair retry.
Permanently absent pairs produce partial completion without losing
successful classifications; diagnostics retain batch raw/parsed output, salvaged rows and errors.

Every primary response is persisted raw before dependent work proceeds. The flow is raw output,
deterministic sanitation, validation, and at most one repair followed by the same sanitation and
validation. Per-pass diagnostics retain both raw outputs, both sanitized payloads, categorized
validation errors, item-level sanitization actions, the final validation status and the final parsed payload. JSON parse, schema,
grounding, and reference failures remain distinct. A second failure is terminal. Generation and
provider failures retain separate categories. Successful prior passes are reused after transient
job retries.

Mamay calls use strict guided JSON and an explicit 4,096-token completion budget. The Pass 2
schema emits `source_entity_id` before `source_kind`, then `epistemic_status`: controlled probes
showed that the previous property orders let the model emit EOS before required fields, leaving
whitespace even when the token budget was raised.

Final results are stored relationally as post-local entities, atomic claims, claim/entity links,
and claim-target classifications. `analysis_runs.final_payload` keeps an inspectable immutable
v4 document, including completion/degradation status. A later completed run of the same revision
marks the earlier completed run `superseded`.

The v3.6 prompts came from a manual review of 200 production posts and a blind comparison on the
100-example golden set (`mamay_vs_golden_v3_6`). Pass 1 keeps named speakers and media and
separates foreign bodies; its prompt keeps the v3.5 rules against repeated, constructed, sentence
or pronoun mentions, without which Mamay looped on repeated mentions until the JSON broke
(primary Pass 1 failed on 59 of 60 such production posts before the fix and none after). Pass 2 does not make a speaker a claim target when the claim is not about
it, extracts evaluative editorial claims expressed through labels, sarcasm, ironic quotation marks,
rhetorical questions or headlines, and treats the news format `…, — X` as attribution to X. Pass 3
classifies the stance of the claim's source: neutral reports of a target's actions or successes,
a target's self-presentation, another actor's attack on a target and polls are `відсутнє`.

v3.7 follows a review of v3.6 errors on all 500 `golden_v0` examples, where v3.6 put stance on
entities that were only background. Pass 1 judges registry candidates as above. Pass 2 links a
claim to an entity when the claim concerns its actions, qualities or evaluation, including its
people, protégés or former staff used against it (`ексдетектив НАБУ брав хабарі`, `протеже Андрія
Єрмака`), but not when the entity is neutral background (`уникнув служби в ЗСУ`, `передав ЗСУ
РЕБи`).
Pass 3 restores the v3.5.2 separation between an event involving the target and the source's own
evaluation: neutral reports of suspicions, searches, exclusions or attacks, neutral background,
statements by the target's own officials, polls, awards and donations, and hostile-source reports
are `відсутнє`.

v4 adds the `targets` pass. Mamay's false negatives were mostly background entities coloured by a
negative event in the same sentence. When the pass offered only a claim's monitored entity IDs,
Mamay's reasons named the right actor («канал критикує Шабуніна») but 37 of 68 false negatives
named an actor that was not on offer (a judge rather than her court, a fund), so constrained
decoding forced the only monitored entity; offering every named actor plus a catch-all, by name,
fixed that. On the 249-post measure-only test split negative F1 was v3.5.2 0.626, v3.6 0.682, v3.7
0.674 and v4 0.728 (v4 - v3.6 +0.047, 95% CI -0.012..+0.106); Claude Haiku 5.5 with the v3.7
prompts reached 0.821. Splitting decisions into narrow calls helped where rewording prompts did
not. Aggregation and product analytics are intentionally deferred.

v4.3 (branch) runs Pass 2 once per monitored entity with that entity as `focus_entity` and merges
the claims; on dev it cut negative pairs lost for lack of a claim from 22 to 6 (negative F1
0.745 → 0.774). v4.4 (branch) adopts the positive-context convention of `golden_v0` v2: Pass 3
labels a target `позитивне` when the source presents it in a positive light even without
explicit praise (successes and results, high trust or ratings, the target's own reports of
success, a favourably framed routine action), keeps flat informational mentions and a target's
praise of others `відсутнє`, and the targets pass counts a favourable presentation as an
evaluation. Under the relabelled gold dev positive recall rose 0.32 → 0.64 (F1 0.442 → 0.655,
+0.213, 95% CI +0.146..+0.287) with negative F1 unchanged.

v4.8 (branch `v4.4-golden-v3`) returns to the v4.4 prompts and adds an `affiliations` call. When
a person in a post with a monitored registry organization receives a negative stance, the call
names the organizations the post itself links each person to (head, member, employee or former
employee; never from model knowledge), and code copies the negative stance and rhetoric to each
linked organization on the same claim. A failed call leaves the classifications unchanged
(`no_propagation`). Migration 016 admits the new pass name.

The previous `extraction_schema_v1` remains packaged only so historical DVC experiments can be
reproduced; it is no longer a production runtime contract.
