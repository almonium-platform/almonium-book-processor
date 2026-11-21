# The writers judge each other: en translation of der-prozess-de-original

Every judge saw the source and the candidates under shuffled letters, without model names. Rank 1 is best; a win is rank 1. Each judge also rated its own work, blind.

## Writing

| Writer | Passages | Output tokens | List price |
|---|---|---|---|
| opus-5.5 | 8 | 36175 | $0.89 |
| gpt-6.1-sol | 8 | 10066 | $0.32 |
| gpt-6-astra | 8 | 9464 | $1.09 |
| gemini-4-carbon-medium | 8 | 131020 | $1.44 |
| gemini-4-argon-medium | 8 | 10075 | $0.27 |
| gemini-4-neon-medium | 8 | 89610 | $1.57 |

## Judge: opus-5.5 (8 passages, $0.93 list)

| Writer | Mean rank | Wins | Mean score | Passages with a slip flagged |
|---|---|---|---|---|
| opus-5.5 (itself) | 2.25 | 2 (25%) | 8.1 | 7 of 8 |
| gpt-6.1-sol | 2.88 | 3 (38%) | 7.9 | 8 of 8 |
| gemini-4-carbon-medium | 3.50 | 2 (25%) | 7.6 | 6 of 8 |
| gpt-6-astra | 4.00 | 0 (0%) | 6.9 | 8 of 8 |
| gemini-4-neon-medium | 4.12 | 0 (0%) | 6.9 | 8 of 8 |
| gemini-4-argon-medium | 4.25 | 1 (12%) | 6.6 | 7 of 8 |

## Judge: gpt-6-astra (8 passages, $1.43 list)

| Writer | Mean rank | Wins | Mean score | Passages with a slip flagged |
|---|---|---|---|---|
| gemini-4-neon-medium | 1.75 | 5 (62%) | 8.8 | 6 of 8 |
| gemini-4-carbon-medium | 2.88 | 2 (25%) | 8.9 | 7 of 8 |
| gpt-6.1-sol | 3.50 | 0 (0%) | 8.4 | 7 of 8 |
| gpt-6-astra (itself) | 3.50 | 0 (0%) | 8.4 | 7 of 8 |
| opus-5.5 | 4.50 | 0 (0%) | 8.1 | 7 of 8 |
| gemini-4-argon-medium | 4.88 | 1 (12%) | 7.6 | 6 of 8 |

## Judge: gemini-4-carbon-medium (6 passages, $3.48 list)

| Writer | Mean rank | Wins | Mean score | Passages with a slip flagged |
|---|---|---|---|---|
| gemini-4-carbon-medium (itself) | 2.67 | 3 (50%) | 7.5 | 6 of 6 |
| gemini-4-neon-medium | 3.17 | 0 (0%) | 6.5 | 6 of 6 |
| opus-5.5 | 3.50 | 2 (33%) | 6.2 | 6 of 6 |
| gpt-6-astra | 3.50 | 1 (17%) | 5.8 | 6 of 6 |
| gemini-4-argon-medium | 4.00 | 0 (0%) | 5.3 | 6 of 6 |
| gpt-6.1-sol | 4.17 | 0 (0%) | 5.7 | 6 of 6 |

## All judges together

| Writer | Mean rank | Wins | Mean score | Rank by itself | Rank by the other judges |
|---|---|---|---|---|---|
| gemini-4-neon-medium | 3.00 | 5 (23%) | 7.5 | - | - |
| gemini-4-carbon-medium | 3.05 | 7 (32%) | 8.0 | 2.67 | 3.19 |
| opus-5.5 | 3.41 | 4 (18%) | 7.6 | 2.25 | 4.07 |
| gpt-6.1-sol | 3.45 | 3 (14%) | 7.5 | - | - |
| gpt-6-astra | 3.68 | 1 (5%) | 7.1 | 3.50 | 3.79 |
| gemini-4-argon-medium | 4.41 | 2 (9%) | 6.6 | - | - |

## Agreement on the best candidate

- opus-5.5 and gpt-6-astra: same best candidate on 1 of 8 passages
- opus-5.5 and gemini-4-carbon-medium: same best candidate on 1 of 6 passages
- gpt-6-astra and gemini-4-carbon-medium: same best candidate on 1 of 6 passages

## Slips flagged, for a person to check

- c0 / gpt-6.1-sol, by opus-5.5: 'NOVEL' alone is a stiff calque of 'ROMAN'; English title pages use 'A NOVEL'
- c0 / gemini-4-neon-medium, by opus-5.5: 'NOVEL' alone is a stiff calque of 'ROMAN'; English title pages use 'A NOVEL'
- c0 / gemini-4-neon-medium, by opus-5.5: 'BINDING DESIGN' is a literal calque of 'Einbandentwurf'; the English credit line is 'COVER DESIGN'
- c0 / gpt-6-astra, by opus-5.5: 'NOVEL' alone is a stiff calque of 'ROMAN'; English title pages use 'A NOVEL'
- c0 / gpt-6-astra, by opus-5.5: 'BINDING DESIGN' is a literal calque of 'Einbandentwurf'; the English credit line is 'COVER DESIGN'
- c1 / opus-5.5, by opus-5.5: 'now the officials had hidden the inspector' drops 'in turn' (wieder)
- c1 / gpt-6.1-sol, by opus-5.5: 'like a trained horse' adds a simile for 'die hohe Schule reiten'
- c1 / gpt-6.1-sol, by opus-5.5: 'purpose' for Sinn breaks the Sinn/sinnlos echo in K.'s outburst
- c1 / gemini-4-neon-medium, by opus-5.5: 'muscular twitch' for Muskelzerrung (strain)
- c1 / gemini-4-neon-medium, by opus-5.5: 'May be' for 'Mag sein' reads as a typo for 'Maybe'
- c1 / gemini-4-argon-medium, by opus-5.5: 'muscular twitch' for Muskelzerrung (strain)
- c1 / gemini-4-argon-medium, by opus-5.5: 'folded hood at the back' invents a detail; the German has only Hinterdeck (rear deck)
- c1 / gemini-4-argon-medium, by opus-5.5: 'cab' for Wagen adds a detail the source doesn't give
- c1 / gpt-6-astra, by opus-5.5: 'offer himself up for arrest' mistranslates 'ihnen seine Verhaftung anzubieten' (offer them his arrest)
- c1 / gpt-6-astra, by opus-5.5: 'There are more spectators over there' drops 'solche'
- c1 / gpt-6-astra, by opus-5.5: 'purpose' for Sinn weakens the Sinn/sinnlos wordplay
- c2 / gemini-4-neon-medium, by opus-5.5: 'this time however misleading' misreads 'mißverständlich': the murmur came from a misunderstanding.
- c2 / gemini-4-neon-medium, by opus-5.5: 'forewent' is the wrong word; the past tense is 'forwent'.
- c2 / gemini-4-neon-medium, by opus-5.5: The word order is often stiff and too literal, as in 'stood on a very low, likewise overcrowded platform a small table'.
- c2 / gemini-4-carbon-medium, by opus-5.5: 'must not be repeated again' is redundant.
- c2 / gemini-4-argon-medium, by opus-5.5: The numerals '1 Stunde und 5 Minuten' are written out as 'one hour and five minutes', which loses Kafka's odd official style.
- c2 / gemini-4-argon-medium, by opus-5.5: 'must never be repeated again' strengthens 'nicht mehr' and is redundant.
- c2 / gpt-6.1-sol, by opus-5.5: 'from time to time' mistranslates 'zeitweilig', which means temporarily.
- c2 / gpt-6.1-sol, by opus-5.5: 'this time it was misleading' misreads 'mißverständlich': the murmur came from a misunderstanding.
- c2 / opus-5.5, by opus-5.5: 'now he too glanced quickly down' wrongly suggests that someone else had glanced; in the original, 'auch' adds a second action by the same man.
- c2 / gpt-6-astra, by opus-5.5: 'from time to time' mistranslates 'zeitweilig', which means temporarily.
- c2 / gpt-6-astra, by opus-5.5: 'its meaning was unclear' mistranslates 'mißverständlich', which means based on a misunderstanding.
- c3 / gpt-6.1-sol, by opus-5.5: "O bitte gewiß" becomes "Oh, certainly, I beg your pardon": the apology is added and the line reads oddly.
- c3 / gpt-6.1-sol, by opus-5.5: "glaubte man ihm nicht" becomes "if the man did not believe", which narrows Kafka's impersonal "man" to the one waiting man.
- c3 / gpt-6.1-sol, by opus-5.5: "griff sogar mit der Hand hin" becomes "reached out to touch it", which adds an actual touch.
- c3 / gemini-4-argon-medium, by opus-5.5: "Erledigung" is rendered as "settlement", which misses the sense of the applications being dealt with.
- c3 / gemini-4-argon-medium, by opus-5.5: "z. B." is kept as "e.g." in literary dialogue.
- c3 / gemini-4-argon-medium, by opus-5.5: "only few people" is unidiomatic.
- c3 / gemini-4-argon-medium, by opus-5.5: "They yielded back a little" is awkward.
- c3 / gemini-4-argon-medium, by opus-5.5: "if they did not believe him that he was accused" is ungrammatical calque.
- c3 / gpt-6-astra, by opus-5.5: "O bitte gewiß" becomes "Oh, certainly, sir": "sir" is invented and "bitte" is lost.
- c3 / gpt-6-astra, by opus-5.5: "Der Herr hier" becomes "The gentleman", dropping "hier".
- c3 / gemini-4-carbon-medium, by opus-5.5: The phrase "unconsciously invited to do so…" is moved, so it separates "took him by the arm" from "as though he wished to compel him".
- c3 / gemini-4-carbon-medium, by opus-5.5: "wenigstens der Farbe nach" becomes "at least in color, consisted of", which weakens the 'judging by' hedge.
- c3 / gemini-4-carbon-medium, by opus-5.5: "At almost regular intervals from one another" is redundant and stiff.
- c3 / gemini-4-neon-medium, by opus-5.5: "Abteilungen des Dachbodens" becomes "departments of the attic", the wrong word for partitioned attic compartments.
- c3 / gemini-4-neon-medium, by opus-5.5: "glaubte man ihm nicht" becomes "if the man did not believe", which narrows the impersonal subject.
- c3 / opus-5.5, by opus-5.5: The temporal "da das die Folgenden sahen" is mistranslated as causal "since those next to them saw this", and the result is a comma splice.
- c3 / opus-5.5, by opus-5.5: "the usher said to them" is joined to the previous clause with a comma splice.
- c8 / gpt-6.1-sol, by opus-5.5: 'even as recently as a week ago' drops the hedge 'etwa' (perhaps)
- c8 / gpt-6.1-sol, by opus-5.5: 'turn a little of the abilities' changes the original's 'turn these abilities a little' toward the trial
- c8 / opus-5.5, by opus-5.5: 'his uncle had already drawn him to the lawyer' is too literal and reads stiffly
- c8 / opus-5.5, by opus-5.5: 'when he was just then swamped with work' is awkward
- c8 / opus-5.5, by opus-5.5: 'withdraw the representation from the lawyer' is clumsy, unidiomatic English
- c8 / gpt-6-astra, by opus-5.5: 'Formerly, as recently as a week ago' drops the hedge 'etwa'
- c8 / gpt-6-astra, by opus-5.5: 'a little of the ability' makes the plural 'Fähigkeiten' singular and changes what 'a little' applies to
- c8 / gpt-6-astra, by opus-5.5: 'contrived' adds a hint of scheming that 'verstanden' (knew how) does not have
- c8 / gemini-4-argon-medium, by opus-5.5: 'For exaggerated anxiety there was, to be sure, no reason for the present' follows German word order and reads stiffly
- c8 / gemini-4-argon-medium, by opus-5.5: 'withdraw the representation from the advocate' is clumsy, unidiomatic English
- c8 / gemini-4-argon-medium, by opus-5.5: 'maintain himself in this position recognized by all' is awkward and missing a comma
- c8 / gemini-4-carbon-medium, by opus-5.5: 'any guilt whatever' adds emphasis the original does not have
- c8 / gemini-4-carbon-medium, by opus-5.5: 'even as little as a week ago' drops the hedge 'etwa'
- c8 / gemini-4-carbon-medium, by opus-5.5: 'heaped with work' is awkward English
- c8 / gemini-4-carbon-medium, by opus-5.5: 'pressure exerted ... that consideration be given to it' is stilted
- c8 / gemini-4-neon-medium, by opus-5.5: 'Even though K. trusted himself' turns the concessive 'even if' (wenn ... auch) into a statement of fact
- c8 / gemini-4-neon-medium, by opus-5.5: 'one could not toy' weakens 'durfte man nicht' (must not)
- c8 / gemini-4-neon-medium, by opus-5.5: 'Formerly, as recently as a week ago' drops the hedge 'etwa'
- c8 / gemini-4-neon-medium, by opus-5.5: 'entered with great laughter' is unidiomatic
- c9 / gpt-6.1-sol, by opus-5.5: 'hitherto quite foreign' adds 'quite', which is not in the German
- c9 / gpt-6.1-sol, by opus-5.5: 'could no longer comprehend' leaves out 'gar nicht' ('at all')
- c9 / opus-5.5, by opus-5.5: 'I knew' leaves out the particle 'ja' ('of course')
- c9 / opus-5.5, by opus-5.5: 'lose their time' is a Germanism; English says 'waste their time'
- c9 / opus-5.5, by opus-5.5: 'let letters out of one's hands to such people' has awkward word order
- c9 / gpt-6-astra, by opus-5.5: 'Sir' drops the title 'Herr Prokurist' (Chief Clerk)
- c9 / gemini-4-argon-medium, by opus-5.5: 'Mr. Chief Clerk' is a stiff, unidiomatic rendering of the title
- c9 / gemini-4-argon-medium, by opus-5.5: 'That he would write to Titorelli he had really only said' keeps German word order
- c9 / gemini-4-carbon-medium, by opus-5.5: 'Not always did someone stand beside him' is stiff inverted syntax
- c9 / gemini-4-carbon-medium, by opus-5.5: 'tell me briefly just now' is an odd rendering of 'jetzt kurz'
- c9 / gemini-4-carbon-medium, by opus-5.5: 'came again shortly' is slightly off for 'nächstens'
- c9 / gemini-4-neon-medium, by opus-5.5: 'accompanied the manufacturer through the anteroom as well' mistranslates 'noch', which means 'on through' here, not 'as well'
- c9 / gemini-4-neon-medium, by opus-5.5: 'if you came another time' loses the sense of 'soon' in 'nächstens'
- c9 / gemini-4-neon-medium, by opus-5.5: 'how heavily the snowfall had increased' is awkward English
- c17 / opus-5.5, by opus-5.5: 'At first I thought' for 'Früher dachte ich': 'formerly' fits better than 'at first'.
- c17 / opus-5.5, by opus-5.5: 'taken every possible pains' is ungrammatical English.
- c17 / opus-5.5, by opus-5.5: 'shrieked' is stronger than 'schrie', and the same cry is later called 'shouted'.
- c17 / gemini-4-neon-medium, by opus-5.5: 'Here we are all human beings' drops the 'doch' ('after all').
- c17 / gemini-4-neon-medium, by opus-5.5: 'for then he had made the confession' copies the German tense and reads stiffly in English.
- c17 / gpt-6-astra, by opus-5.5: 'lifting one hand from the parapet': the source has the hand raised on the parapet, not from it.
- c17 / gpt-6-astra, by opus-5.5: 'it is not true help' drops the article: the source says 'die wahre Hilfe' ('the true help').
- c17 / gpt-6-astra, by opus-5.5: 'He did so and the priest beckoned him nearer with a finger' recasts the passive and loses 'Winken des Fingers'.
- c17 / gpt-6.1-sol, by opus-5.5: 'raising one hand from the parapet': the source has the hand raised on the parapet, not from it.
- c17 / gpt-6.1-sol, by opus-5.5: 'What a storm might be raging outside?' is ungrammatical as a question.
- c17 / gpt-6.1-sol, by opus-5.5: 'Above him all remained silent' adds 'him'.
- c17 / gemini-4-carbon-medium, by opus-5.5: 'At bottom he too was nothing else' puts 'auch' on the wrong word.
- c17 / gemini-4-carbon-medium, by opus-5.5: 'the size of the cathedral seemed to him, too': 'auch' here means 'and also', not 'to him too'.
- c17 / gemini-4-carbon-medium, by opus-5.5: 'Can you really not see' adds 'really', which is not in the source.
- c17 / gemini-4-argon-medium, by opus-5.5: 'Leave essentials aside' reverses the meaning of 'Laß das Nebensächliche', which means 'leave aside what is incidental'.
- c17 / gemini-4-argon-medium, by opus-5.5: 'Look you' is invented; nothing in the source corresponds to it.
- c17 / gemini-4-argon-medium, by opus-5.5: 'Lay it out of your hand' is an unidiomatic word-for-word rendering.
- c17 / gemini-4-argon-medium, by opus-5.5: 'Yet I am not guilty' is a weak rendering of 'aber' in this line.
- c17 / gemini-4-argon-medium, by opus-5.5: 'At first I thought' for 'Früher': 'formerly' fits better.
- c18 / gemini-4-argon-medium, by opus-5.5: "showing me from the outside the note" is an ambiguous, over-literal rendering of "von außen"
- c18 / gemini-4-argon-medium, by opus-5.5: "publication might disconcert further work": "disconcert" is the wrong word to use with "work"
- c18 / gemini-4-argon-medium, by opus-5.5: "abrogates" is stronger than "derogiert", which means to detract from or partly override
- c18 / gemini-4-argon-medium, by opus-5.5: "In case you should seriously expect" is unidiomatic for "Falls … im Ernste"
- c18 / gemini-4-argon-medium, by opus-5.5: "novellas" for "Novellen" is a false-friend rendering; these are stories
- c18 / gemini-4-argon-medium, by opus-5.5: "What does ever so grave a conflict … weigh" is awkward English
- c18 / opus-5.5, by opus-5.5: "a whole series of motives" overstates "eine Reihe", which means a number
- c18 / opus-5.5, by opus-5.5: "showing me from the outside the note" is ambiguous
- c18 / gpt-6-astra, by opus-5.5: "no longer troubles him" adds "him", which is not in "jetzt nicht mehr stört"
- c18 / gpt-6-astra, by opus-5.5: "it will hopefully be done" uses a modern sentence-adverb "hopefully" that does not fit the period voice
- c18 / gpt-6-astra, by opus-5.5: "dabei" ("on such occasions") is omitted from the clause about hidden earnestness
- c18 / gpt-6.1-sol, by opus-5.5: "without opening it" interprets "von außen" instead of translating it
- c18 / gpt-6.1-sol, by opus-5.5: "no longer troubles him" adds "him"
- c18 / gpt-6.1-sol, by opus-5.5: "such 'even' artistically unsuccessful works" has an awkward word order
- c18 / gemini-4-carbon-medium, by opus-5.5: "abrogates" is stronger than "derogiert"
- c18 / gemini-4-carbon-medium, by opus-5.5: "such 'even' artistically unsuccessful works" has an awkward word order
- c18 / gemini-4-carbon-medium, by opus-5.5: "showing me from the outside the slip of paper" is ambiguous
- c18 / gemini-4-neon-medium, by opus-5.5: "which he was bound to foresee" shifts "mußte voraussehen" ("must have foreseen") slightly
- c18 / gemini-4-neon-medium, by opus-5.5: "abrogates" is stronger than "derogiert"
- c18 / gemini-4-neon-medium, by opus-5.5: "such 'even' artistically failed works" has an awkward word order
- c1 / gemini-4-argon-medium, by gpt-6-astra: “Chronic muscular twitch” mistranslates “chronische Muskelzerrung”: a chronic muscular strain.
- c1 / gemini-4-argon-medium, by gpt-6-astra: “Uncharacteristic” means atypical, whereas these young men are nondescript.
- c1 / gemini-4-argon-medium, by gpt-6-astra: “Folded hood” substitutes an unsupported object for the motorcar’s rear deck.
- c1 / gemini-4-argon-medium, by gpt-6-astra: “Doubtless” strengthens the inspector’s tentative “wohl.”
- c1 / gemini-4-argon-medium, by gpt-6-astra: “Go through my paces” reduces the specific high-school riding image.
- c1 / gemini-4-argon-medium, by gpt-6-astra: Capitalizing “Bank” treats an ordinary noun as a proper name.
- c1 / gemini-4-argon-medium, by gpt-6-astra: The dialogue tag in “To the Bank?” asked K., “I thought…” should end with a period.
- c1 / gemini-4-neon-medium, by gpt-6-astra: “Chronic muscular twitch” mistranslates “chronische Muskelzerrung”: a chronic muscular strain.
- c1 / gemini-4-neon-medium, by gpt-6-astra: “No doubt” strengthens the inspector’s tentative “wohl.”
- c1 / gemini-4-neon-medium, by gpt-6-astra: “Go through my paces” reduces the specific high-school riding image.
- c1 / gemini-4-neon-medium, by gpt-6-astra: “Back of the automobile” loses the specific rear deck.
- c1 / gemini-4-neon-medium, by gpt-6-astra: The dialogue tag in “To the bank?” asked K., “I thought…” should end with a period.
- c1 / gemini-4-carbon-medium, by gpt-6-astra: “Go through my paces” reduces the specific high-school riding image.
- c1 / gemini-4-carbon-medium, by gpt-6-astra: The dialogue tag in “To the bank?” asked K., “I thought…” should end with a period.
- c1 / gpt-6-astra, by gpt-6-astra: “Purpose” breaks the repeated verbal connection between “Sinn” and “sinnlos.”
- c1 / gpt-6-astra, by gpt-6-astra: “More spectators” drops “solche,” K.’s identification of spectators of the same sort.
- c1 / gpt-6-astra, by gpt-6-astra: “Offer himself up for arrest” replaces the deliberately peculiar “offer them his arrest.”
- c1 / gpt-6-astra, by gpt-6-astra: “Hardly … necessary” strengthens “not very necessary.”
- c1 / gpt-6-astra, by gpt-6-astra: “Rear of the motor-car” loses the specific rear deck.
- c1 / gpt-6-astra, by gpt-6-astra: The dialogue tag in “To the bank?” asked K., “I thought…” should end with a period.
- c1 / gpt-6.1-sol, by gpt-6-astra: “Purpose” breaks the repeated verbal connection between “Sinn” and “sinnlos.”
- c1 / gpt-6.1-sol, by gpt-6-astra: “Like a trained horse” changes K.’s role in the riding image from rider to performing horse.
- c1 / gpt-6.1-sol, by gpt-6-astra: “Scarcely … necessary” strengthens “not very necessary.”
- c1 / gpt-6.1-sol, by gpt-6-astra: “Rear of the motor-car” loses the specific rear deck.
- c1 / gpt-6.1-sol, by gpt-6-astra: “Could … have done with encouragement” softens the explicit need for encouragement.
- c1 / gpt-6.1-sol, by gpt-6-astra: The dialogue tag in “To the bank?” asked K., “I thought…” should end with a period.
- c1 / opus-5.5, by gpt-6-astra: “It’s senseless, though” introduces a contrast absent from “es ist ja sinnlos.”
- c1 / opus-5.5, by gpt-6-astra: “Must be at an end” strengthens the tentative “dürfte … beendet sein.”
- c1 / opus-5.5, by gpt-6-astra: “Uncharacteristic” means atypical, whereas these young men are nondescript.
- c1 / opus-5.5, by gpt-6-astra: The dialogue tag in “To the bank?” asked K., “I thought…” should end with a period.
- c2 / gemini-4-carbon-medium, by gpt-6-astra: “Under a misapprehension” makes the murmuring mistaken rather than misleading or liable to misunderstanding.
- c2 / gemini-4-carbon-medium, by gpt-6-astra: “The latter resting his elbow ... and his legs crossed” is grammatically unbalanced.
- c2 / gemini-4-carbon-medium, by gpt-6-astra: “Observe rather than to speak” weakens the explicit comparison: observe more than speak.
- c2 / gpt-6-astra, by gpt-6-astra: “Rubbed sore” substitutes friction for the pressure injury conveyed by “wundzudrücken”.
- c2 / gpt-6-astra, by gpt-6-astra: “Its meaning was unclear” shifts “mißverständlich” from misleading to merely unclear.
- c2 / gemini-4-argon-medium, by gpt-6-astra: “Local political meeting” loses the specific district designation.
- c2 / gemini-4-argon-medium, by gpt-6-astra: “Rub themselves raw” substitutes friction for pressure and intensifies the injury.
- c2 / gemini-4-argon-medium, by gpt-6-astra: “Observe rather than to speak” weakens the explicit comparison: observe more than speak.
- c2 / gemini-4-argon-medium, by gpt-6-astra: “Too late” adds a suggestion of missed opportunity to K.’s concession of lateness.
- c2 / gemini-4-argon-medium, by gpt-6-astra: “Resting on a misunderstanding” asserts a mistaken basis for the murmuring.
- c2 / gemini-4-argon-medium, by gpt-6-astra: “The others for the time being” drops the additive force of “auch”.
- c2 / gemini-4-neon-medium, by gpt-6-astra: “Chafe themselves” substitutes friction for the pressure injury conveyed by “wundzudrücken”.
- c2 / gemini-4-neon-medium, by gpt-6-astra: “Forewent” should be “forwent” in the sense of dispensing with a defense.
- c2 / gemini-4-neon-medium, by gpt-6-astra: “Examining Magistrate’s” unnecessarily capitalizes a descriptive office.
- c2 / gpt-6.1-sol, by gpt-6-astra: “Had ... been left clear” introduces an implication of prior clearance absent from “frei war”.
- c2 / gpt-6.1-sol, by gpt-6-astra: “Rubbed sore” substitutes friction for the pressure injury conveyed by “wundzudrücken”.
- c2 / gpt-6.1-sol, by gpt-6-astra: “A burst of applause” adds sudden intensity absent from the source.
- c2 / opus-5.5, by gpt-6-astra: “Local political meeting” loses the specific district designation.
- c2 / opus-5.5, by gpt-6-astra: “Now he too glanced” incorrectly attaches “also” to the man rather than his additional glance into the hall.
- c2 / opus-5.5, by gpt-6-astra: “Rub themselves sore” substitutes friction for the pressure injury conveyed by “wundzudrücken”.
- c2 / opus-5.5, by gpt-6-astra: “A burst of applause” adds sudden intensity absent from the source.
- c2 / opus-5.5, by gpt-6-astra: “Based on a misunderstanding” asserts a mistaken basis for the murmuring.
- c3 / gemini-4-carbon-medium, by gpt-6-astra: “Each following the example of the next” replaces the unspecified other person with the next person.
- c3 / gemini-4-carbon-medium, by gpt-6-astra: “Wearied K. once and for all” misplaces the force of endgültig: the screaming finally makes him lose patience.
- c3 / gemini-4-neon-medium, by gpt-6-astra: “Making a joke at his expense” adds a suggestion of targeted ridicule to “mache mit ihm einen Scherz.”
- c3 / gemini-4-neon-medium, by gpt-6-astra: The comma after “Not everyone thinks as you do,” said K. incorrectly joins two independent dialogue sentences.
- c3 / gpt-6.1-sol, by gpt-6-astra: “How humbled” softens the humiliation expressed by “Wie gedemütigt.”
- c3 / gpt-6.1-sol, by gpt-6-astra: “Each following the example of the next” specifies a sequence absent from the original.
- c3 / gpt-6.1-sol, by gpt-6-astra: “I beg your pardon” introduces an apology into “O bitte gewiß.”
- c3 / gpt-6.1-sol, by gpt-6-astra: “Only touched him” weakens the light grasp described in context.
- c3 / gpt-6.1-sol, by gpt-6-astra: The comma after “Not everyone thinks as you do,” said K. incorrectly joins two independent dialogue sentences.
- c3 / gemini-4-argon-medium, by gpt-6-astra: “Waiting for the settlement” suggests resolution of the case rather than disposal of the evidentiary motions.
- c3 / gemini-4-argon-medium, by gpt-6-astra: “Only few people” is unidiomatic here; English requires “only a few people.”
- c3 / gemini-4-argon-medium, by gpt-6-astra: “They yielded back” is an unnatural rendering of their stepping back.
- c3 / gemini-4-argon-medium, by gpt-6-astra: “I, e.g.” imports a written abbreviation into spoken dialogue.
- c3 / gemini-4-argon-medium, by gpt-6-astra: “If they did not believe him that he was accused” uses an unidiomatic English construction.
- c3 / gemini-4-argon-medium, by gpt-6-astra: The comma after “Not everyone thinks as you do,” said K. incorrectly joins two independent dialogue sentences.
- c3 / opus-5.5, by gpt-6-astra: “Usher” omits the explicit court designation in Gerichtsdiener.
- c3 / opus-5.5, by gpt-6-astra: “Those next to them” narrows the successive people farther along the benches to immediate neighbors.
- c3 / opus-5.5, by gpt-6-astra: “Making a joke at his expense” adds a suggestion of targeted ridicule.
- c3 / opus-5.5, by gpt-6-astra: “Only touched him” weakens the light grasp described in context.
- c3 / opus-5.5, by gpt-6-astra: “Weary of him” makes the man explicitly the object of K.’s impatience where the original leaves that unspecified.
- c3 / opus-5.5, by gpt-6-astra: The greeting sequence and the gathering around the group contain awkward English comma splices.
- c3 / opus-5.5, by gpt-6-astra: The comma after “Not everyone thinks as you do,” said K. incorrectly joins two independent dialogue sentences.
- c3 / gpt-6-astra, by gpt-6-astra: “Their knees bowed” suggests outward curvature rather than knees bent in a submissive stance.
- c3 / gpt-6-astra, by gpt-6-astra: “Making fun of him” strengthens jesting into ridicule.
- c3 / gpt-6-astra, by gpt-6-astra: “Oh, certainly, sir” adds an honorific and drops the pleading bitte.
- c3 / gpt-6-astra, by gpt-6-astra: “Only touched him” weakens the light grasp described in context.
- c3 / gpt-6-astra, by gpt-6-astra: The comma after “Not everyone thinks as you do,” said K. incorrectly joins two independent dialogue sentences.
- c8 / gemini-4-neon-medium, by gpt-6-astra: 'Listlessly' weakens 'willenlos': the thoughts pass without his willing or directing them.
- c8 / gemini-4-neon-medium, by gpt-6-astra: 'Would not be able to let up' changes a prohibition against relenting into an inability to relent.
- c8 / gemini-4-neon-medium, by gpt-6-astra: 'As recently as a week ago' drops the approximation in 'etwa'.
- c8 / gemini-4-carbon-medium, by gpt-6-astra: 'Hold fast as far as possible' blurs 'möglichst festhalten', which emphasizes holding as firmly as possible.
- c8 / gemini-4-carbon-medium, by gpt-6-astra: 'Even as little as a week ago' drops the approximation in 'etwa'.
- c8 / gpt-6-astra, by gpt-6-astra: 'As recently as a week ago' drops the approximation in 'etwa'.
- c8 / gpt-6-astra, by gpt-6-astra: 'Positively overwhelmed' adds emphasis where 'gerade' marks the work occupying him at that moment.
- c8 / gpt-6-astra, by gpt-6-astra: The final 'and which' grammatically makes the joke, rather than the required drawing, what the deputy manager draws.
- c8 / opus-5.5, by gpt-6-astra: 'Irrefutable' makes the conviction logically unanswerable rather than psychologically inescapable ('unabweisbar').
- c8 / opus-5.5, by gpt-6-astra: 'Dared to carry all this through' substitutes courage for confidence in his ability ('sich ... getraute').
- c8 / gemini-4-argon-medium, by gpt-6-astra: 'Listlessly' weakens the absence of volitional control expressed by 'willenlos'.
- c8 / gemini-4-argon-medium, by gpt-6-astra: 'Hold fast as far as possible' blurs the emphasis on holding as firmly as possible.
- c8 / gemini-4-argon-medium, by gpt-6-astra: 'Very painful' obscures the specific embarrassment expressed by 'sehr peinlich' here.
- c8 / gemini-4-argon-medium, by gpt-6-astra: Capitalizing 'Bank' and 'Court' imports German noun capitalization without an English proper-name justification.
- c8 / gpt-6.1-sol, by gpt-6-astra: 'Even as recently as a week ago' drops the approximation in 'etwa'.
- c8 / gpt-6.1-sol, by gpt-6-astra: 'Positively overwhelmed' adds emphasis where 'gerade' marks what occupied him at that moment.
- c8 / gpt-6.1-sol, by gpt-6-astra: The final 'and which' grammatically makes the joke, rather than the drawing, what the deputy manager executes.
- c9 / gemini-4-neon-medium, by gpt-6-astra: “Another time” loses the near-future sense of “nächstens.”
- c9 / gemini-4-neon-medium, by gpt-6-astra: “How heavily the snowfall had increased” is an unidiomatic rendering of the snowfall becoming much heavier.
- c9 / gpt-6-astra, by gpt-6-astra: “Sir” omits the occupational title in “Herr Prokurist.”
- c9 / gpt-6-astra, by gpt-6-astra: “I beg your pardon” drops the emphasis of “sehr.”
- c9 / gpt-6-astra, by gpt-6-astra: “An urgent matter of business” loses the specific sense of an errand in “Geschäftsgang.”
- c9 / gpt-6-astra, by gpt-6-astra: “Had asked the attendant to bring” substitutes a request for the completed arrangement expressed by “hatte … bringen lassen.”
- c9 / gemini-4-carbon-medium, by gpt-6-astra: Capitalizing “Bank” treats an ordinary institutional noun as a proper name without justification.
- c9 / gpt-6.1-sol, by gpt-6-astra: “Could no longer comprehend” drops the explicit emphasis of “gar nicht mehr.”
- c9 / gpt-6.1-sol, by gpt-6-astra: “Quite foreign” adds an intensifier absent from “bisher fremde.”
- c9 / opus-5.5, by gpt-6-astra: “I knew” loses the reassuring emphasis of “Ich wußte ja.”
- c9 / opus-5.5, by gpt-6-astra: “Let them lose their time” is unidiomatic English for “ihre Zeit verlieren zu lassen.”
- c17 / gemini-4-carbon-medium, by gpt-6-astra: “There were no evasions” obscures the meaning that no evasion was possible.
- c17 / gemini-4-carbon-medium, by gpt-6-astra: Several direct questions retain German commas or full stops instead of English question marks.
- c17 / gemini-4-carbon-medium, by gpt-6-astra: The spoken call “Josef K.!” lacks quotation marks.
- c17 / gemini-4-neon-medium, by gpt-6-astra: “Overrun the court table and the accused” is an awkward English rendering of physically trampling or charging over them.
- c17 / gemini-4-neon-medium, by gpt-6-astra: The spoken call “Josef K.!” lacks quotation marks.
- c17 / gpt-6.1-sol, by gpt-6-astra: “Without being able to make out precisely where” adds an inability absent from “without determining the place precisely.”
- c17 / gpt-6.1-sol, by gpt-6-astra: “May never get beyond a lower court” loses the emphatic “even” in “gar nicht hinauskommen.”
- c17 / gpt-6.1-sol, by gpt-6-astra: “What a storm might be raging outside?” turns a question about the kind of storm into an awkward exclamatory construction.
- c17 / gpt-6.1-sol, by gpt-6-astra: Several direct questions retain German commas or full stops instead of English question marks.
- c17 / gpt-6-astra, by gpt-6-astra: “Without being able to determine the spot exactly” adds an inability not explicitly stated in the source.
- c17 / gpt-6-astra, by gpt-6-astra: “Measured progression” weakens the regular, law-governed progression conveyed by “gesetzmäßigem Fortschreiten.”
- c17 / gpt-6-astra, by gpt-6-astra: “May never get beyond a lower court” loses the emphatic “even” in “gar nicht hinauskommen.”
- c17 / gpt-6-astra, by gpt-6-astra: The questions about human guilt and true help end with full stops.
- c17 / opus-5.5, by gpt-6-astra: “I have taken every possible pains” is ungrammatical English.
- c17 / opus-5.5, by gpt-6-astra: “At first” narrows “Früher,” which means formerly or previously.
- c17 / opus-5.5, by gpt-6-astra: “Run down the court table” is an unsuitable English expression for charging or trampling over it.
- c17 / opus-5.5, by gpt-6-astra: Several direct questions retain German commas or full stops instead of English question marks.
- c17 / opus-5.5, by gpt-6-astra: The spoken call “Josef K.!” lacks quotation marks.
- c17 / gemini-4-argon-medium, by gpt-6-astra: “Leave essentials aside” reverses “Laß das Nebensächliche”: the priest dismisses incidental matters.
- c17 / gemini-4-argon-medium, by gpt-6-astra: “Look you” is an invented interjection.
- c17 / gemini-4-argon-medium, by gpt-6-astra: “Against his own will” changes an involuntary cry into one contrary to the speaker's wishes.
- c17 / gemini-4-argon-medium, by gpt-6-astra: “There were no evasions” obscures the meaning that no evasion was possible.
- c17 / gemini-4-argon-medium, by gpt-6-astra: “Lay it out of your hand” is an unidiomatic literal rendering of the instruction to put the album down.
- c17 / gemini-4-argon-medium, by gpt-6-astra: “At first” narrows “Früher,” which means formerly or previously.
- c18 / gemini-4-carbon-medium, by gpt-6-astra: “Forced ... every single publication from Kafka” is unidiomatic English for securing publication through persistent pressure.
- c18 / gpt-6-astra, by gpt-6-astra: “No longer troubles him” adds a personal object and narrows the source’s unspecified sense of no longer interfering.
- c18 / gemini-4-argon-medium, by gpt-6-astra: “Disconcert further work” wrongly applies a verb for unsettling a person to work; “disrupt” fits here.
- c18 / gemini-4-argon-medium, by gpt-6-astra: “Forced ... every single publication from Kafka” is unidiomatic English.
- c18 / gemini-4-argon-medium, by gpt-6-astra: “Novellas” imposes an English length category that German “Novellen” does not necessarily imply.
- c18 / gemini-4-argon-medium, by gpt-6-astra: “The ‘Hunger Artist’” mishandles the English title “A Hunger Artist.”
- c18 / opus-5.5, by gpt-6-astra: “Postcard” omits the picture specified by “Ansichtskarte.”
- c18 / gpt-6.1-sol, by gpt-6-astra: “Without opening it” invents a physical action or condition; the source says he showed the note from the outside.
- c18 / gpt-6.1-sol, by gpt-6-astra: “No longer troubles him” adds a personal object and narrows the source’s unspecified sense of no longer interfering.
- c0 / gpt-6-astra, by gemini-4-carbon-medium: Bare 'NOVEL' calques 'ROMAN' where English title-page convention expects 'A NOVEL'.
- c0 / gemini-4-neon-medium, by gemini-4-carbon-medium: Bare 'NOVEL' calques 'ROMAN' where English title-page convention expects 'A NOVEL'.
- c0 / gemini-4-argon-medium, by gemini-4-carbon-medium: 'COVER DESIGN' generalizes 'EINBANDENTWURF', which specifically denotes binding design ('Einband' vs. 'Umschlag').
- c0 / opus-5.5, by gemini-4-carbon-medium: 'COVER DESIGN' generalizes 'EINBANDENTWURF', which specifically denotes binding design ('Einband' vs. 'Umschlag').
- c0 / gemini-4-carbon-medium, by gemini-4-carbon-medium: 'COVER DESIGN' generalizes 'EINBANDENTWURF', which specifically denotes binding design ('Einband' vs. 'Umschlag').
- c0 / gpt-6.1-sol, by gemini-4-carbon-medium: Bare 'NOVEL' calques 'ROMAN' where English title-page convention expects 'A NOVEL'.
- c0 / gpt-6.1-sol, by gemini-4-carbon-medium: 'COVER DESIGN' generalizes 'EINBANDENTWURF', which specifically denotes binding design ('Einband' vs. 'Umschlag').
- c2 / opus-5.5, by gemini-4-carbon-medium: Mistranslates 'sah nun auch schnell in den Saal hinunter' as 'now he too glanced...', misattaching 'auch' to the subject.
- c2 / opus-5.5, by gemini-4-carbon-medium: Renders 'Meldung' as 'announcement' instead of a quiet message or report to one person.
- c2 / opus-5.5, by gemini-4-carbon-medium: Omits 'noch' in 'ich will es jedoch ausnahmsweise heute noch tun'.
- c2 / opus-5.5, by gemini-4-carbon-medium: Omits 'hinunter-' in 'hinunterhängenden' ('loosely hanging') and 'mehr' in 'nicht mehr wiederholen'.
- c2 / opus-5.5, by gemini-4-carbon-medium: Generalizes 'Bezirksversammlung' ('district meeting') to 'local political meeting' and renders 'Verspätung' as 'delay'.
- c2 / gemini-4-argon-medium, by gemini-4-carbon-medium: Mistranslates 'mehr zu beobachten als zu reden' as 'to observe rather than to speak', omitting 'mehr'.
- c2 / gemini-4-argon-medium, by gemini-4-carbon-medium: Omits 'auch' twice: in 'auch die andern' and in 'vielleicht auch diesen selbst'.
- c2 / gemini-4-argon-medium, by gemini-4-carbon-medium: Renders 'Parteien' as 'factions', losing the verbal link to 'political meeting', and generalizes 'Bezirks-' to 'local'.
- c2 / gemini-4-argon-medium, by gemini-4-carbon-medium: Replaces indefinite 'etwas' in 'etwas auszurichten' with 'his message' and omits 'hindurch' and 'hinunter-' ('loosely hanging').
- c2 / gemini-4-argon-medium, by gemini-4-carbon-medium: Unidiomatic phrasing: 'the ceiling of the room' ('Zimmerdecke'), 'never be repeated again', and 'onto which he climbed up'.
- c2 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Mistranslates 'mehr zu beobachten als zu reden' as 'to observe rather than to speak', omitting 'mehr'.
- c2 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Ungrammatical clause 'the latter resting his elbow... and his legs crossed', also dropping pluperfect 'hatte... gestützt'.
- c2 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Archaic, unnatural conditional inversion 'did he not wish to push' and unidiomatic 'press themselves sore' and 'repeated again'.
- c2 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Renders 'Parteien' as 'factions', 'kleiner' (man) as 'short', 'etwas' ('etwas auszurichten') as 'his errand', and 'diesen' as 'the man'.
- c2 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Omits the second 'nun' in 'und sah nun auch schnell in den Saal hinunter' and turns several finite clauses into participles.
- c2 / gpt-6.1-sol, by gemini-4-carbon-medium: Mistranslates 'zeitweilig' ('temporarily / for a time') as 'from time to time'.
- c2 / gpt-6.1-sol, by gemini-4-carbon-medium: Mistranslates 'mißverständlich' ('based on a misunderstanding') as 'though this time it was misleading'.
- c2 / gpt-6.1-sol, by gemini-4-carbon-medium: Softens 'dicker' ('fat') to 'stout', 'großem Gelächter' to 'much laughter', and 'Es war' to 'It belonged to'.
- c2 / gpt-6.1-sol, by gemini-4-carbon-medium: Renders 'Parteien' as 'factions' and drops the litotes of 'hörten nicht auf' ('went on').
- c2 / gpt-6.1-sol, by gemini-4-carbon-medium: Omits 'noch' ('heute noch'), 'auch' ('diesen selbst'), 'etwas' ('etwas antworten'), and 'hinunter-' twice, and reorders clauses.
- c2 / gpt-6-astra, by gemini-4-carbon-medium: Mistranslates 'zeitweilig' ('temporarily / for a time') as 'from time to time'.
- c2 / gpt-6-astra, by gemini-4-carbon-medium: Mistranslates 'mißverständlich' ('based on a misunderstanding') as 'though this time its meaning was unclear'.
- c2 / gpt-6-astra, by gemini-4-carbon-medium: Renders 'Kommen Sie, kommen Sie' as 'Come, come', which in English conveys chiding impatience rather than 'Come along'.
- c2 / gpt-6-astra, by gemini-4-carbon-medium: Softens 'großem Gelächter' to 'much laughter' and 'hinaufstieg' ('climbed up') to 'stepped up'.
- c2 / gpt-6-astra, by gemini-4-carbon-medium: Omits 'noch' ('heute noch'), 'auch' ('diesen selbst'), 'etwas' ('etwas antworten'), and 'hinunter-' twice, and reorders clauses.
- c2 / gemini-4-neon-medium, by gemini-4-carbon-medium: Mistranslates 'mißverständlich' ('based on a misunderstanding') as 'this time however misleading' (also missing commas).
- c2 / gemini-4-neon-medium, by gemini-4-carbon-medium: Renders 'Kommen Sie, kommen Sie' as 'Come, come' (chiding idiom) and 'sich gerade... unterhielt' as 'was just conversing'.
- c2 / gemini-4-neon-medium, by gemini-4-carbon-medium: Unidiomatic calques: 'what also spoke for this was that', 'political district meeting', 'wanted to answer something', and triple 'however'.
- c2 / gemini-4-neon-medium, by gemini-4-carbon-medium: Capitalizes 'Examining Magistrate’s' against English convention and weakens 'sich nicht wundzudrücken' to 'not to chafe themselves'.
- c2 / gemini-4-neon-medium, by gemini-4-carbon-medium: Omits 'noch' ('heute noch'), 'auch' ('diesen selbst'), and 'hinunter-' ('off the platform'), and strands 'amid great laughter' after the dash.
- c1 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "private matter of your own" adds "of your own" to "irgendeine private Angelegenheit".
- c1 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "make me go through my paces" softens the dressage image "die hohe Schule reiten".
- c1 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "What sense there would be ...?" calques German subordinate-clause word order ungrammatically as a question.
- c1 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "The old couple" (twice) over-specifies "Die Alten" ("the old people").
- c1 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "There are spectators of the same sort over there" omits "auch" ("too").
- c1 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "promptly drew back a few steps at once" misses confirmative "auch" and duplicates "sofort".
- c1 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "If you share my opinion" omits "auch" ("you too").
- c1 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "massive bulk" replaces "mächtigen Leib" ("massive body").
- c1 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "Do not look across" mistranslates "hin" ("over there") as "across".
- c1 / gemini-4-neon-medium, by gemini-4-carbon-medium: "The Public Prosecutor Hasterer" and "a Public Prosecutor" misuse the article and capitalization for English titles.
- c1 / gemini-4-neon-medium, by gemini-4-carbon-medium: "what sense that could have" stiffly calques "welchen Sinn das haben sollte".
- c1 / gemini-4-neon-medium, by gemini-4-carbon-medium: "soften a stone" calques "zum Steinerweichen" literally instead of an English idiom.
- c1 / gemini-4-neon-medium, by gemini-4-carbon-medium: "make me go through my paces" softens the dressage image "die hohe Schule reiten".
- c1 / gemini-4-neon-medium, by gemini-4-carbon-medium: "What sense it would have ...?" calques German subordinate-clause word order ungrammatically as a question.
- c1 / gemini-4-neon-medium, by gemini-4-carbon-medium: Comma splice in "'Well, gentlemen,' cried K., it seemed to him for a moment...".
- c1 / gemini-4-neon-medium, by gemini-4-carbon-medium: "May be," writes "Mag sein" unidiomatically as two words instead of "That may be" or "Maybe".
- c1 / gemini-4-neon-medium, by gemini-4-carbon-medium: "pay close attention" adds "close" to "auf alle Worte aufpassen".
- c1 / gemini-4-neon-medium, by gemini-4-carbon-medium: "These so featureless, anemic young men" calques German syntax ("Diese so...").
- c1 / gemini-4-neon-medium, by gemini-4-carbon-medium: "muscular twitch" mistranslates "Muskelzerrung" ("muscle strain").
- c1 / gemini-4-neon-medium, by gemini-4-carbon-medium: "Well then, we shall go to work" omits "Nun" ("now").
- c1 / gemini-4-neon-medium, by gemini-4-carbon-medium: "No explanation was necessary, however" omits "auch" ("either").
- c1 / gemini-4-argon-medium, by gemini-4-carbon-medium: "Was he to receive ... Was he to be punished" adds prospective obligation to past-tense "bekam" and "wurde ... bestraft".
- c1 / gemini-4-argon-medium, by gemini-4-carbon-medium: "private matter of your own" adds "of your own" to "irgendeine private Angelegenheit".
- c1 / gemini-4-argon-medium, by gemini-4-carbon-medium: "make me go through my paces" softens the dressage image "die hohe Schule reiten".
- c1 / gemini-4-argon-medium, by gemini-4-carbon-medium: "What sense there would be ...?" calques German subordinate-clause word order ungrammatically as a question.
- c1 / gemini-4-argon-medium, by gemini-4-carbon-medium: "wanted to rise" mistranslates "wollten sich erheben" ("were about to rise").
- c1 / gemini-4-argon-medium, by gemini-4-carbon-medium: "pressed one hand firmly flat ... comparing the fingers according to their length" adds "flat" and calques "ihrer Länge nach" awkwardly.
- c1 / gemini-4-argon-medium, by gemini-4-carbon-medium: "that need not hinder you" softens "das soll Sie nicht hindern" ("is not to hinder you").
- c1 / gemini-4-argon-medium, by gemini-4-carbon-medium: "These so uncharacteristic" mistranslates "uncharakteristischen" ("nondescript/featureless") with a false friend and German syntax.
- c1 / gemini-4-argon-medium, by gemini-4-carbon-medium: "muscular twitch" mistranslates "Muskelzerrung" ("muscle strain").
- c1 / gemini-4-argon-medium, by gemini-4-carbon-medium: "folded hood at the back of the motor-car" invents "folded hood" for "Hinterdeck" ("rear deck").
- c1 / gemini-4-argon-medium, by gemini-4-carbon-medium: Over-capitalizes common nouns "Inspector" and "Bank" throughout and shifts between "motor-car" and "cab".
- c1 / gpt-6.1-sol, by gemini-4-carbon-medium: "The public prosecutor Hasterer" uses an unidiomatic definite article before title and name.
- c1 / gpt-6.1-sol, by gemini-4-carbon-medium: Translating "Sinn" as "purpose" alongside "senseless" ("Sinnloseste") loses the central "Sinn/sinnlos" wordplay.
- c1 / gpt-6.1-sol, by gemini-4-carbon-medium: "move a stone" truncates "zum Steinerweichen", losing the sense of moving a stone to pity.
- c1 / gpt-6.1-sol, by gemini-4-carbon-medium: "perform before you like a trained horse" turns the metaphor "die hohe Schule reiten" into an explicit simile.
- c1 / gpt-6.1-sol, by gemini-4-carbon-medium: "stepped up to his window" invents "his" (the room is Fräulein Bürstner's, not K.'s).
- c1 / gpt-6.1-sol, by gemini-4-carbon-medium: "by shaking hands. If you share my opinion ... held out his hand" omits "gegenseitigen" ("mutual"), "auch" ("too"), and "ihm" ("to him").
- c1 / gpt-6.1-sol, by gemini-4-carbon-medium: "trying on a new hat" changes plural "neuer Hüte" to singular, and "you were saying?" mistranslates "meinten Sie?" ("you thought?").
- c1 / gpt-6.1-sol, by gemini-4-carbon-medium: Omits hedges and connectives: "Damit" ("With that"), "auch" ("Darum wiederholte er auch"), "sehr" ("sehr notwendig"), "also" ("Nun werden wir also"), and "übrigens auch".
- c1 / gpt-6.1-sol, by gemini-4-carbon-medium: "front door" renders "Haustor" ("street/house gate") ambiguously.
- c1 / gpt-6.1-sol, by gemini-4-carbon-medium: "pallid" softens "blutarmen" ("anemic/bloodless").
- c1 / gpt-6.1-sol, by gemini-4-carbon-medium: Comma splices in "...muscular strain, 'Good morning!' said K." and "...seemed tired, Rabensteiner looked out...".
- c1 / gpt-6.1-sol, by gemini-4-carbon-medium: "in the hope of perhaps catching sight" omits "noch" ("still") and adds "in the hope of", clashing with the next sentence.
- c1 / opus-5.5, by gemini-4-carbon-medium: "Was he to be given ... Was he to be punished" adds prospective obligation to past-tense "bekam" and "wurde ... bestraft".
- c1 / opus-5.5, by gemini-4-carbon-medium: "It's senseless, though" mistranslates emphatic "ja" in "es ist ja sinnlos" as "though".
- c1 / opus-5.5, by gemini-4-carbon-medium: "What sense there would be ...?" calques German subordinate-clause word order ungrammatically as a question.
- c1 / opus-5.5, by gemini-4-carbon-medium: "wanted to get up" mistranslates "wollten sich erheben" ("were about to get up").
- c1 / opus-5.5, by gemini-4-carbon-medium: Omits "Damit" ("With that") in "That is enough for today" and "auch" in "That was why he repeated".
- c1 / opus-5.5, by gemini-4-carbon-medium: "front door" renders "Haustor" ("street/house gate") ambiguously.
- c1 / opus-5.5, by gemini-4-carbon-medium: "These so uncharacteristic" mistranslates "uncharakteristischen" ("nondescript/featureless") with a false friend and German syntax.
- c1 / opus-5.5, by gemini-4-carbon-medium: Comma splices in "...muscle strain, 'Good morning!' said K." and "...seemed tired, Rabensteiner looked out...".
- c1 / opus-5.5, by gemini-4-carbon-medium: Uneven register mixes colloquial contractions ("It's", "don't", "didn't") with formal "I shall not telephone" and "haute école".
- c1 / gpt-6-astra, by gemini-4-carbon-medium: "It is all quite senseless" adds "all", and "The public prosecutor Hasterer" misuses the definite article before a title and name.
- c1 / gpt-6-astra, by gemini-4-carbon-medium: Translating "Sinn" as "purpose" alongside "senseless" ("Sinnloseste") loses the "Sinn/sinnlos" wordplay.
- c1 / gpt-6-astra, by gemini-4-carbon-medium: "move a stone" truncates "zum Steinerweichen", losing the sense of moving a stone to pity.
- c1 / gpt-6-astra, by gemini-4-carbon-medium: "There are more spectators over there" omits "solche" ("such / of that sort").
- c1 / gpt-6-astra, by gemini-4-carbon-medium: "by shaking hands. If you share my opinion, then pray ... held out his hand" omits "gegenseitigen", "auch", and "ihm", and uses overly archaic "pray".
- c1 / gpt-6-astra, by gemini-4-carbon-medium: "trying on a new hat" changes plural "neuer Hüte" to singular.
- c1 / gpt-6-astra, by gemini-4-carbon-medium: Omits "Damit" ("With that"), "sehr" ("sehr notwendig"), and "übrigens auch".
- c1 / gpt-6-astra, by gemini-4-carbon-medium: "front door" blurs "Haustor", and "offer himself up for arrest" normalizes "ihnen seine Verhaftung anzubieten" while omitting "ihnen".
- c1 / gpt-6-astra, by gemini-4-carbon-medium: Multiple comma splices and syntax breaks: "cried K., for a moment...", "...strain, 'Good morning!'", "only when K. missed his hat ... they all ran", and "...weary, Rabensteiner...".
- c1 / gpt-6-astra, by gemini-4-carbon-medium: "in the hope of perhaps catching another glimpse" adds "in the hope of", clashing with the next sentence.
- c3 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "einiges Licht" ("some light") slightly diminished to "a little light"
- c3 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "Ich weiß nicht genau" ("exactly") rendered as "I do not know for certain"
- c3 / gemini-4-neon-medium, by gemini-4-carbon-medium: "es sind Angeklagte" narrowed twice to "accused men"
- c3 / gemini-4-neon-medium, by gemini-4-carbon-medium: "Dann sind es ja meine Kollegen": realization particle "ja" misrendered as "after all"
- c3 / gemini-4-neon-medium, by gemini-4-carbon-medium: "Sie scheinen sich ja viele Mühe zu geben": emphatic "ja" omitted
- c3 / gemini-4-neon-medium, by gemini-4-carbon-medium: "Ich weiß nicht genau" ("exactly") rendered as "I do not know for certain"
- c3 / gemini-4-neon-medium, by gemini-4-carbon-medium: "am liebsten" ("liked best") softened to "preferred"
- c3 / gemini-4-neon-medium, by gemini-4-carbon-medium: "glaubte man ihm nicht" (impersonal "man") mistranslated as "if the man did not believe"
- c3 / gpt-6-astra, by gemini-4-carbon-medium: "war es doch nicht vollständig dunkel": omits "doch" and softens "vollständig" to "quite"
- c3 / gpt-6-astra, by gemini-4-carbon-medium: "In fast regelmäßigen Entfernungen voneinander": omits "voneinander" ("from one another")
- c3 / gpt-6-astra, by gemini-4-carbon-medium: "Gesichtsausdruck": omits "Gesichts-" ("facial"), pluralizing to "expressions"
- c3 / gpt-6-astra, by gemini-4-carbon-medium: "niemals vollständig aufrecht": softens "vollständig" ("completely") to "quite"
- c3 / gpt-6-astra, by gemini-4-carbon-medium: "die Knie geknickt" ("bent/buckled") wrong word "their knees bowed" (suggests bow-legged)
- c3 / gpt-6-astra, by gemini-4-carbon-medium: Omits modal "ja" in "Dann sind es ja meine Kollegen" and "Sie scheinen sich ja viele Mühe zu geben"
- c3 / gpt-6-astra, by gemini-4-carbon-medium: "Der Herr hier fragt ja nur": omits "hier" ("here")
- c3 / gpt-6-astra, by gemini-4-carbon-medium: "Ich weiß nicht genau" ("exactly") softened to "I do not really know"
- c3 / gpt-6-astra, by gemini-4-carbon-medium: "mache mit ihm einen Scherz" ("playing a joke") distorted to "making fun of him"
- c3 / gpt-6-astra, by gemini-4-carbon-medium: "O bitte gewiß": invents "sir" ("Oh, certainly, sir")
- c3 / gpt-6-astra, by gemini-4-carbon-medium: "Dieses lächerliche Schreien" ("screaming") wrong word "crying" (suggests weeping), and "des Schreins" made singular "the cry"
- c3 / opus-5.5, by gemini-4-carbon-medium: "der Gerichtsdiener" reduced to "the usher" throughout (8 times), omitting "court"
- c3 / opus-5.5, by gemini-4-carbon-medium: "glaubten sie auch grüßen zu müssen": ungrammatical intransitive "had to greet"
- c3 / opus-5.5, by gemini-4-carbon-medium: "es sind Angeklagte" narrowed in the first clause to "they are accused men"
- c3 / opus-5.5, by gemini-4-carbon-medium: Omits modal "ja" in "Dann sind es ja meine Kollegen" and "Sie scheinen sich ja viele Mühe zu geben"
- c3 / opus-5.5, by gemini-4-carbon-medium: "machte K. endgültig überdrüssig": invents "of him" ("weary of him"), narrowing K.'s general disgust
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: "rohe gezimmerte Türen" ("roughly carpentered doors") altered to "roughly fashioned wooden doors"
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: "war es doch nicht vollständig dunkel": omits "doch"
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: "In fast regelmäßigen Entfernungen voneinander": omits "voneinander" ("from one another")
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: "Gesichtsausdruck": omits "Gesichts-" ("facial"), pluralizing to "expressions"
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: "niemals vollständig aufrecht": softens "vollständig" ("completely") to "quite"
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: "Wie gedemütigt" ("humiliated") softened to "How humbled"
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: Omits modal "ja" in "Dann sind es ja meine Kollegen" and "Sie scheinen sich ja viele Mühe zu geben"
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: "gewiß sich zu beherrschen verstand und ... nicht leicht aufgab": turns indicative facts into speculative "must surely have known ... and would not readily relinquish"
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: "es ist ja meine Sache": adds "own" ("my own case")
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: "Halten Sie denn das für nötig?": omits "denn"
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: "Ich weiß nicht genau" softened to "I do not quite know", and "am liebsten" softened to "preferred"
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: "nicht mit zwei Fingern, sondern mit einer glühenden Zange": reverses contrast to "with red-hot pincers instead of two fingers"
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: "Dieses lächerliche Schreien" ("screaming") wrong word "crying" (suggests weeping)
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: "glaubte man ihm nicht" (impersonal "man") mistranslated as "if the man did not believe"
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: "griff sogar mit der Hand hin": invents purpose "to touch it"
- c3 / gpt-6.1-sol, by gemini-4-carbon-medium: "durch Gicht abgemessenen Schritten": loses image "measured out", flattening to "their length probably determined by gout"
- c3 / gemini-4-argon-medium, by gemini-4-carbon-medium: "nur wenig Leute": ungrammatical omission of article in "only few people"
- c3 / gemini-4-argon-medium, by gemini-4-carbon-medium: "glaubten sie auch grüßen zu müssen": ungrammatical intransitive "had to greet as well"
- c3 / gemini-4-argon-medium, by gemini-4-carbon-medium: "es sind Angeklagte" narrowed twice to "accused men"
- c3 / gemini-4-argon-medium, by gemini-4-carbon-medium: "Dann sind es ja meine Kollegen": realization particle "ja" misrendered as "after all"
- c3 / gemini-4-argon-medium, by gemini-4-carbon-medium: "Sie wichen ein wenig zurück": unidiomatic "yielded back"
- c3 / gemini-4-argon-medium, by gemini-4-carbon-medium: "warte auf die Erledigung" ("disposition") mistranslated as "waiting for the settlement"
- c3 / gemini-4-argon-medium, by gemini-4-carbon-medium: "es ist ja meine Sache": modal "ja" mistranslated as conjunction "for it is my case"
- c3 / gemini-4-argon-medium, by gemini-4-carbon-medium: "ich z. B. bin auch angeklagt": leaves raw abbreviation "I, e.g.," in spoken dialogue
- c3 / gemini-4-argon-medium, by gemini-4-carbon-medium: "noch auch sonst": redundant "nor ... either" after "neither"
- c3 / gemini-4-argon-medium, by gemini-4-carbon-medium: "Dieses lächerliche Schreien" and "wegen des Schreins" ("screaming") wrong word "crying"
- c3 / gemini-4-argon-medium, by gemini-4-carbon-medium: "glaubte man ihm nicht, daß er angeklagt war": ungrammatical calque "believe him that he was accused"
- c3 / gemini-4-argon-medium, by gemini-4-carbon-medium: "faßte ihn ... wirklich fester": unidiomatic calque "gripped him really more firmly"
- c17 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Mistranslates modal 'auch' in 'Im Grunde war er auch nichts anderes' as 'At bottom he too was nothing else.'
- c17 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Misattaches connective 'auch' in 'auch schien ihm die Größe des Doms' as 'seemed to him, too, to lie.'
- c17 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Softens the hunting image of 'Frauenjägern' to 'womanizers' and shifts 'um nur rechtzeitig hinzukommen' to 'if only to get there in time.'
- c17 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Leaves 'Josef K.!' unquoted and retains German commas/periods instead of English question marks on four spoken questions.
- c17 / gpt-6-astra, by gemini-4-carbon-medium: Changes impersonal 'es' ('it') to 'he' in 'he would succeed even without K.’s assistance.'
- c17 / gpt-6-astra, by gemini-4-carbon-medium: Softens 'gesetzmäßigem' ('regular / law-governed') to 'measured' in 'measured progression.'
- c17 / gpt-6-astra, by gemini-4-carbon-medium: Translates 'auf der Brüstung' ('on the parapet') as 'from the parapet.'
- c17 / gpt-6-astra, by gemini-4-carbon-medium: Omits modal particles 'denn' and 'doch' ('after all') in 'Wie kann denn ein Mensch... Wir sind hier doch alle Menschen.'
- c17 / gpt-6-astra, by gemini-4-carbon-medium: Renders 'den Unbeteiligten' ('the uninvolved') ambiguously as 'those who are not concerned.'
- c17 / gpt-6-astra, by gemini-4-carbon-medium: Omits 'die' ('the') and 'denn' in 'daß es nicht die wahre Hilfe ist' ('that it is not true help') and softens 'fremde Hilfe' to 'help from others.'
- c17 / gpt-6-astra, by gemini-4-carbon-medium: Uses unidiomatic literal compound 'woman-hunters' for 'Frauenjägern.'
- c17 / gpt-6-astra, by gemini-4-carbon-medium: Renders 'Was für ein Unwetter' ('What sort of storm') as 'What storm' and adds 'raging.'
- c17 / gpt-6-astra, by gemini-4-carbon-medium: Omits 'doch' ('after all') in 'Es sind doch nur meine Erfahrungen' and 'noch immer' ('still') in 'Above him all remained silent' (adding 'him').
- c17 / gpt-6-astra, by gemini-4-carbon-medium: Omits 'von' ('by') in the final sentence ('It was shouted ... like someone' instead of 'as if by someone') and leaves periods on two spoken questions.
- c17 / gpt-6.1-sol, by gemini-4-carbon-medium: Omits 'jetzt' ('now') in the opening clause ('ob er sich jetzt nicht eiligst entfernen sollte').
- c17 / gpt-6.1-sol, by gemini-4-carbon-medium: Changes impersonal 'es' ('it') to 'he' in 'he would succeed even without K.’s assistance.'
- c17 / gpt-6.1-sol, by gemini-4-carbon-medium: Translates 'auf der Brüstung' ('on the parapet') as 'from the parapet' and adds colloquial 'round' in 'show an Italian round the cathedral.'
- c17 / gpt-6.1-sol, by gemini-4-carbon-medium: Omits modal particles 'denn' and 'doch' ('after all') in 'Wie kann denn ein Mensch... Wir sind hier doch alle Menschen.'
- c17 / gpt-6.1-sol, by gemini-4-carbon-medium: Renders 'den Unbeteiligten' ('the uninvolved') ambiguously as 'those who are not concerned' and softens 'fremde Hilfe' to 'help from others.'
- c17 / gpt-6.1-sol, by gemini-4-carbon-medium: Renders 'überrennt' awkwardly as 'will run over' and 'zwei Schritte weit' as 'two steps before you.'
- c17 / gpt-6.1-sol, by gemini-4-carbon-medium: Mistranslates interrogative 'Was für ein Unwetter mochte draußen sein?' as exclamatory 'What a storm might be raging outside?' and adds 'raging.'
- c17 / gpt-6.1-sol, by gemini-4-carbon-medium: Omits 'doch' ('after all') in 'Es sind doch nur meine Erfahrungen' and 'noch immer' ('still') in 'Above him all remained silent' (adding 'him').
- c17 / gpt-6.1-sol, by gemini-4-carbon-medium: Retains German commas/periods instead of English question marks on four spoken questions.
- c17 / gemini-4-argon-medium, by gemini-4-carbon-medium: Mistranslates 'Laß das Nebensächliche' ('Leave aside what is incidental') as its antonym, 'Leave essentials aside.'
- c17 / gemini-4-argon-medium, by gemini-4-carbon-medium: Invents 'Look you,' before 'for the time being at least,' with nothing corresponding in the German.
- c17 / gemini-4-argon-medium, by gemini-4-carbon-medium: Calques 'Leg es aus der Hand' unidiomatically as 'Lay it out of your hand.'
- c17 / gemini-4-argon-medium, by gemini-4-carbon-medium: Translates 'die Eingabe' ('the petition') as 'my petition' and omits modal 'auch' in 'Im Grunde war er auch nichts anderes.'
- c17 / gemini-4-neon-medium, by gemini-4-carbon-medium: Renders affirmative modal 'auch' in 'Im Grunde war er auch nichts anderes' as negative 'either.'
- c17 / gemini-4-neon-medium, by gemini-4-carbon-medium: Omits 'ganz' ('quite') in 'es war ganz eindeutig' ('it was unmistakable').
- c17 / gemini-4-neon-medium, by gemini-4-carbon-medium: Calques German indicative pluperfect ungrammatically as 'for then he had made the confession' in a conditional sentence.
- c17 / gemini-4-neon-medium, by gemini-4-carbon-medium: Uses wrong English idiom 'with a wave of his finger' for beckoning ('durch ein Winken des Fingers').
- c17 / gemini-4-neon-medium, by gemini-4-carbon-medium: Uses unidiomatic calques 'with whom he was meeting,' 'I did not know it,' and 'Up above it still remained silent.'
- c17 / gemini-4-neon-medium, by gemini-4-carbon-medium: Translates 'Prozeß' as courtroom 'trial' and 'Hauptaltar' as 'main altar' instead of 'high altar.'
- c17 / gemini-4-neon-medium, by gemini-4-carbon-medium: Omits 'doch' ('after all') and misorders 'Wir sind hier doch alle Menschen' as 'Here we are all human beings.'
- c17 / gemini-4-neon-medium, by gemini-4-carbon-medium: Softens 'Frauenjägern' to 'womanizers,' misattaches 'from a distance,' and uses wrong verb 'overrun' for a single person knocking over a table.
- c17 / gemini-4-neon-medium, by gemini-4-carbon-medium: Omits 'von' ('by') in the final sentence ('It was shouted ... like someone'), keeps '11' as digits, and leaves 'Josef K.!' unquoted.
- c17 / opus-5.5, by gemini-4-carbon-medium: Translates 'Geistliche' throughout as 'clergyman,' clashing in register with the cathedral setting and high altar candles.
- c17 / opus-5.5, by gemini-4-carbon-medium: Renders 'Im Grunde war er auch nichts anderes' with negative 'either' and 'mit krummem Rücken' ('bent back') as 'with his crooked back.'
- c17 / opus-5.5, by gemini-4-carbon-medium: Omits 'zwar' in 'oder daß er zwar verstanden hatte' and 'Ach' in 'Ach so.'
- c17 / opus-5.5, by gemini-4-carbon-medium: Translates 'Prozeß' as 'trial' and renders 'vielleicht ... gar nicht' pleonastically as 'perhaps never ... at all.'
- c17 / opus-5.5, by gemini-4-carbon-medium: Translates 'ein Mensch' as 'any man' right before 'human beings' ('Menschen'), losing the key repetition, and omits 'denn.'
- c17 / opus-5.5, by gemini-4-carbon-medium: Softens 'fremde Hilfe' to 'help from others,' 'durchdringen' to vague 'get through,' and renders 'überrennt' ambiguously as 'run down.'
- c17 / opus-5.5, by gemini-4-carbon-medium: Distorts voice and register by translating 'schrie' as 'shrieked' and 'zwei Schritte' as 'two steps.'
- c17 / opus-5.5, by gemini-4-carbon-medium: Keeps '11' as digits, leaves 'Josef K.!' unquoted, and retains German commas/periods instead of English question marks on four spoken questions.
- c9 / opus-5.5, by gemini-4-carbon-medium: Omits modal 'ja' in '"I knew,"' ('Ich wußte ja') and in 'You have seen for yourselves'.
- c9 / opus-5.5, by gemini-4-carbon-medium: Uses informal contractions ('I'll', 'I'm') and sentence fragment ('Though I did think...') against period register.
- c9 / opus-5.5, by gemini-4-carbon-medium: Misattaches 'an solche Leute' in 'let letters out of one's hands to such people' instead of 'letters to such people'.
- c9 / opus-5.5, by gemini-4-carbon-medium: Uses 'understanding' where 'Verstand' means practical 'judgment'.
- c9 / opus-5.5, by gemini-4-carbon-medium: Calques 'ihre Zeit verlieren' unidiomatically as 'lose their time' instead of 'waste their time'.
- c9 / opus-5.5, by gemini-4-carbon-medium: Renders 'unter dem Halse' ('throat/neck') as 'under his chin'.
- c9 / gemini-4-neon-medium, by gemini-4-carbon-medium: Overstates modal 'ja' as 'very well' in 'I knew very well' and omits 'ja' in 'You have seen for yourselves'.
- c9 / gemini-4-neon-medium, by gemini-4-carbon-medium: Renders 'noch' ambiguously as 'accompanied the manufacturer through the anteroom as well'.
- c9 / gemini-4-neon-medium, by gemini-4-carbon-medium: Softens intrusive 'sich ... an K. heranzumachen' to 'approach K.'.
- c9 / gemini-4-neon-medium, by gemini-4-carbon-medium: Mistranslates ongoing 'sagte schon' with ungrammatical 'one of them already said'.
- c9 / gemini-4-neon-medium, by gemini-4-carbon-medium: Mistranslates 'nächstens' ('soon') as 'another time' inside awkward 'Best of all, however, would be if...'.
- c9 / gemini-4-neon-medium, by gemini-4-carbon-medium: Uses unidiomatic collocation 'how heavily the snowfall had increased' for 'sich ... sehr verstärkt hatte'.
- c9 / gpt-6.1-sol, by gemini-4-carbon-medium: Softens 'zwingen' ('force himself') to 'bring himself' and 'an K. heranzumachen' to 'approach K.'.
- c9 / gpt-6.1-sol, by gemini-4-carbon-medium: Omits directional 'hin-' ('there') in '"I shall go,"' ('Ich werde hingehn').
- c9 / gpt-6.1-sol, by gemini-4-carbon-medium: Shifts 'vorteilhaft' ('advantageous') to 'advisable' and weakens 'durchgedacht' ('through') to 'thought everything over'.
- c9 / gpt-6.1-sol, by gemini-4-carbon-medium: Invents 'venture' in 'what you may venture to do' ('was Sie tun dürfen') and 'quite' in 'hitherto quite foreign'.
- c9 / gpt-6.1-sol, by gemini-4-carbon-medium: Omits particles and intensifiers 'noch', 'auch' ('either'), 'dann' ('then'), 'gar' ('at all'), 'schon' ('already'), and 'ja'.
- c9 / gpt-6.1-sol, by gemini-4-carbon-medium: Inverts sentence structure in 'Yet it was only through...', breaking parallel clause alignment.
- c9 / gpt-6.1-sol, by gemini-4-carbon-medium: Shifts 'sehr' to 'must' in 'I must beg your pardon' and 'wollen' ('want') to 'intend'.
- c9 / gpt-6.1-sol, by gemini-4-carbon-medium: Mistranslates 'K.s Zimmer' ('room') as 'K.’s office' and 'Halse' ('throat') as 'chin'.
- c9 / gpt-6-astra, by gemini-4-carbon-medium: Flattens 'der Schaden, der darin lag, daß' to 'the harm done by' and inverts 'Die Gefahren aber...' sentence order.
- c9 / gpt-6-astra, by gemini-4-carbon-medium: Softens 'zwingen' ('force himself') to 'bring himself' and 'an K. heranzumachen' to 'approach K.'.
- c9 / gpt-6-astra, by gemini-4-carbon-medium: Shifts 'vorteilhaft' ('advantageous') to 'advisable' and weakens 'durchgedacht' ('through') to 'thought everything over'.
- c9 / gpt-6-astra, by gemini-4-carbon-medium: Invents 'venture' in 'what you may venture to do' ('was Sie tun dürfen').
- c9 / gpt-6-astra, by gemini-4-carbon-medium: Omits 'noch', 'auch' ('either'), 'dann' ('then'), 'schon' ('already'), 'sehr' ('I beg your pardon'), and 'ja'.
- c9 / gpt-6-astra, by gemini-4-carbon-medium: Omits the title 'Prokurist' by rendering '"Herr Prokurist,"' generically as '“Sir,”'.
- c9 / gpt-6-astra, by gemini-4-carbon-medium: Mistranslates completed causative 'hatte sich ... bringen lassen' as 'had asked the attendant to bring'.
- c9 / gpt-6-astra, by gemini-4-carbon-medium: Omits the errand sense of '-gang' by rendering 'Geschäftsgang' as 'matter of business'.
- c9 / gpt-6-astra, by gemini-4-carbon-medium: Renders 'unter dem Halse' ('throat/neck') as 'beneath his chin'.
- c9 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Adds 'else' in 'or else' ('oder').
- c9 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Misattaches 'an solche Leute' in 'let letters pass out of one’s hands to such people'.
- c9 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Calques 'zu schätzen wisse' as 'knew how to value' with stiff German inversions ('That he would write...', 'Not always did someone stand...').
- c9 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Softens factual past 'einlud' to 'might invite'.
- c9 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Softens 'so rücksichtslos war' ('was so inconsiderate') to 'so little consideration had been shown'.
- c9 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Mistranslates 'jetzt kurz' ('briefly right now') as 'briefly just now' ('a moment ago').
- c9 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Misrenders 'gewartet haben sollten' ('were now to have waited') as 'were now supposed to have waited'.
- c9 / gemini-4-argon-medium, by gemini-4-carbon-medium: Softens 'konnte' ('could') to 'might bring' and uses unidiomatic 'damage' for abstract 'Schaden' ('harm').
- c9 / gemini-4-argon-medium, by gemini-4-carbon-medium: Calques 'zu schätzen wisse' as 'knew how to appreciate' with stiff German word order ('That he would write...', 'I unfortunately have no time').
- c9 / gemini-4-argon-medium, by gemini-4-carbon-medium: Misplaces 'erst' ('only through') as 'had only recognized through'.
- c9 / gemini-4-argon-medium, by gemini-4-carbon-medium: Misrenders causal 'da' as temporal 'as' with pluperfect ('as the attendant was speaking... they had stood up').
- c9 / gemini-4-argon-medium, by gemini-4-carbon-medium: Softens 'sich ... an K. heranzumachen' to 'approach K.'.
- c9 / gemini-4-argon-medium, by gemini-4-carbon-medium: Violates English title conventions by calquing 'Herr Prokurist' as '"Mr. Chief Clerk,"'.
- c9 / gemini-4-argon-medium, by gemini-4-carbon-medium: Renders 'nächstens' ('soon') clumsily as 'some other time soon'.
- c9 / gemini-4-argon-medium, by gemini-4-carbon-medium: Misrenders 'gewartet haben sollten' ('were now to have waited') as 'were now supposed to have waited'.
