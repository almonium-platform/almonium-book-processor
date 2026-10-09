# The writers judge each other: B1 adaptation of bleak-house-en-original

Every judge saw the source and the candidates under shuffled letters, without model names. Rank 1 is best; a win is rank 1. Each judge also rated its own work, blind.

## Writing

| Writer | Passages | Output tokens | List price |
|---|---|---|---|
| opus-5.5 | 8 | 38421 | $0.96 |
| fable-5.1 | 8 | 34902 | $2.23 |
| gpt-6.1-sol | 8 | 14692 | $0.43 |
| gpt-6-astra | 8 | 14497 | $1.89 |

## Judge: opus-5.5 (8 passages, $0.64 list)

| Writer | Mean rank | Wins | Mean score | Passages with a slip flagged |
|---|---|---|---|---|
| opus-5.5 (itself) | 2.12 | 3 (38%) | 7.1 | 8 of 8 |
| fable-5.1 | 2.12 | 2 (25%) | 7.2 | 8 of 8 |
| gpt-6-astra | 2.75 | 1 (12%) | 6.6 | 8 of 8 |
| gpt-6.1-sol | 3.00 | 2 (25%) | 6.4 | 8 of 8 |

## Judge: fable-5.1 (8 passages, $2.37 list)

| Writer | Mean rank | Wins | Mean score | Passages with a slip flagged |
|---|---|---|---|---|
| fable-5.1 (itself) | 1.38 | 5 (62%) | 7.8 | 8 of 8 |
| opus-5.5 | 1.75 | 3 (38%) | 7.4 | 8 of 8 |
| gpt-6-astra | 3.38 | 0 (0%) | 6.0 | 8 of 8 |
| gpt-6.1-sol | 3.50 | 0 (0%) | 5.9 | 8 of 8 |

## Judge: gpt-6.1-sol (8 passages, $0.40 list)

| Writer | Mean rank | Wins | Mean score | Passages with a slip flagged |
|---|---|---|---|---|
| gpt-6.1-sol (itself) | 2.12 | 3 (38%) | 7.2 | 8 of 8 |
| gpt-6-astra | 2.50 | 2 (25%) | 6.9 | 8 of 8 |
| opus-5.5 | 2.62 | 2 (25%) | 6.9 | 8 of 8 |
| fable-5.1 | 2.75 | 1 (12%) | 6.8 | 8 of 8 |

## Judge: gpt-6-astra (8 passages, $1.79 list)

| Writer | Mean rank | Wins | Mean score | Passages with a slip flagged |
|---|---|---|---|---|
| gpt-6-astra (itself) | 1.38 | 6 (75%) | 8.0 | 7 of 8 |
| gpt-6.1-sol | 2.38 | 2 (25%) | 7.4 | 8 of 8 |
| fable-5.1 | 3.00 | 0 (0%) | 6.8 | 8 of 8 |
| opus-5.5 | 3.25 | 0 (0%) | 6.4 | 8 of 8 |

## All judges together

| Writer | Mean rank | Wins | Mean score | Rank by itself | Rank by the other judges |
|---|---|---|---|---|---|
| fable-5.1 | 2.31 | 8 (25%) | 7.1 | 1.38 | 2.62 |
| opus-5.5 | 2.44 | 8 (25%) | 6.9 | 2.12 | 2.54 |
| gpt-6-astra | 2.50 | 9 (28%) | 6.9 | 1.38 | 2.88 |
| gpt-6.1-sol | 2.75 | 7 (22%) | 6.7 | 2.12 | 2.96 |

## Agreement on the best candidate

- opus-5.5 and fable-5.1: same best candidate on 2 of 8 passages
- opus-5.5 and gpt-6.1-sol: same best candidate on 4 of 8 passages
- opus-5.5 and gpt-6-astra: same best candidate on 1 of 8 passages
- fable-5.1 and gpt-6.1-sol: same best candidate on 2 of 8 passages
- fable-5.1 and gpt-6-astra: same best candidate on 0 of 8 passages
- gpt-6.1-sol and gpt-6-astra: same best candidate on 3 of 8 passages

## Slips flagged, for a person to check

- c7 / fable-5.1, by opus-5.5: 'without taking such a freedom' is an awkward, unidiomatic phrase
- c7 / fable-5.1, by opus-5.5: 'sits as judge in the Inn' adds a small explanation
- c7 / opus-5.5, by opus-5.5: 'as if at a christening' adds an explanation and keeps a hard word
- c7 / opus-5.5, by opus-5.5: 'parchmentses' keeps a nonstandard form that will confuse a B1 reader
- c7 / opus-5.5, by opus-5.5: 'He don't notice me' and 'pretty well every day' keep dialect that is not explained
- c7 / opus-5.5, by opus-5.5: 'good sign, or omen' adds a gloss
- c7 / gpt-6-astra, by opus-5.5: Invented 'Usually, the lady's attention wandered from one thing to another' as an added explanation
- c7 / gpt-6-astra, by opus-5.5: 'documents written on animal skin' explains 'parchment' instead of translating it
- c7 / gpt-6-astra, by opus-5.5: 'any fish that comes into my net is welcome' leaves the idiom in, taken literally
- c7 / gpt-6-astra, by opus-5.5: 'Lord Chancellor' title kept without the 'noble' sense; 'great and learned man' is a loose rendering
- c7 / gpt-6.1-sol, by opus-5.5: Invented 'Usually, the old lady's attention wandered from one thing to another' as an added explanation
- c7 / gpt-6.1-sol, by opus-5.5: 'old documents on animal skin' explains 'parchment' instead of translating it
- c7 / gpt-6.1-sol, by opus-5.5: 'everything that comes into my net is useful to me' leaves the idiom in, taken literally, and changes its meaning
- c7 / gpt-6.1-sol, by opus-5.5: 'that great lord with all his learning' loosens 'noble and learned brother'
- c15 / opus-5.5, by opus-5.5: 'they are most remarkable men' uses the present tense, but both men are dead
- c15 / opus-5.5, by opus-5.5: 'a kind of red wine' is an added gloss
- c15 / fable-5.1, by opus-5.5: 'elegant and polite meal' – 'polite' is the wrong word for 'genteel' when describing a dinner
- c15 / fable-5.1, by opus-5.5: 'the first-class man that Captain Swosser so very much was' is awkward and unidiomatic
- c15 / fable-5.1, by opus-5.5: 'a kind of red wine' is an added gloss
- c15 / gpt-6.1-sol, by opus-5.5: 'confidently' misreads 'in a tone of confidence', which means confidentially
- c15 / gpt-6.1-sol, by opus-5.5: 'So we heard all about them' loses the irony of 'we had the full benefit of them'
- c15 / gpt-6.1-sol, by opus-5.5: 'the Professor's cup with a stem' is a clumsy substitute for 'goblet'
- c15 / gpt-6.1-sol, by opus-5.5: 'They were men of the very highest quality' is an added sentence
- c15 / gpt-6.1-sol, by opus-5.5: 'a red wine' is an added gloss
- c15 / gpt-6-astra, by opus-5.5: 'confidently' misreads 'in a tone of confidence', which means confidentially
- c15 / gpt-6-astra, by opus-5.5: 'He gave Ada and me the honour' changes 'we had the honour of being under his care'
- c15 / gpt-6-astra, by opus-5.5: 'we enjoyed the full benefit of hearing about them' adds an explanation
- c15 / gpt-6-astra, by opus-5.5: 'You will find it a very special and unusual wine' adds 'special' to 'curious'
- c15 / gpt-6-astra, by opus-5.5: 'drinking cup—the one with the stem' is an awkward paraphrase of 'goblet'
- c15 / gpt-6-astra, by opus-5.5: 'a kind of red wine' is an added gloss
- c23 / fable-5.1, by opus-5.5: 'scatters... so fast' invents speed not in the source
- c23 / fable-5.1, by opus-5.5: 'short curly dark hair' adds 'short'
- c23 / fable-5.1, by opus-5.5: 'a trooper, a soldier on horseback' adds an explanation
- c23 / fable-5.1, by opus-5.5: 'circulation, the flow of my blood' puts an explanation into the dialogue
- c23 / opus-5.5, by opus-5.5: keeps "'Druidical ruins'" unexplained, too hard for B1, and doesn't show the ruins are the bread
- c23 / opus-5.5, by opus-5.5: 'mean' for 'pinched ways' suggests stinginess
- c23 / opus-5.5, by opus-5.5: 'a trooper, a soldier on horseback' adds an explanation
- c23 / gpt-6-astra, by opus-5.5: 'like those left by the Druids, ancient priests' adds an explanation and doesn't link the ruins to the bread
- c23 / gpt-6-astra, by opus-5.5: adds an explanation of spurs ('metal points riders wear on their boots to urge horses on')
- c23 / gpt-6-astra, by opus-5.5: changes the dialect to standard English ('How do you do', 'haven't'), losing the voice
- c23 / gpt-6-astra, by opus-5.5: 'trooper' is dropped and becomes 'a soldier who rode a horse'
- c23 / gpt-6-astra, by opus-5.5: 'take the whole family into his own body' is awkward and too literal
- c23 / gpt-6.1-sol, by opus-5.5: 'like those of the Druids, ancient priests' adds an explanation and doesn't link the ruins to the bread
- c23 / gpt-6.1-sol, by opus-5.5: adds an explanation of spurs
- c23 / gpt-6.1-sol, by opus-5.5: 'The tea is like a tide flowing out' is vague and loses the low-tide picture
- c23 / gpt-6.1-sol, by opus-5.5: changes the dialect to standard English ('How do you do', 'haven't')
- c23 / gpt-6.1-sol, by opus-5.5: keeps the old-fashioned 'Perhaps you do right', hard at B1
- c31 / gpt-6-astra, by opus-5.5: 'damn it' / 'Damn these notes' is a stronger oath than 'dash it' and changes Guppy's tone
- c31 / gpt-6-astra, by opus-5.5: 'Perhaps your ladyship' changes Guppy's 'I think your ladyship'
- c31 / gpt-6-astra, by opus-5.5: Changes the opening formula to 'Thank you, your ladyship'
- c31 / gpt-6.1-sol, by opus-5.5: 'Mr. Guppy thanks her' is a mistranslation: in the source, 'does so' means he takes the seat he was offered
- c31 / gpt-6.1-sol, by opus-5.5: 'damn it' / 'Damn these notes' makes the mild oath 'dash it' stronger
- c31 / gpt-6.1-sol, by opus-5.5: 'no one would have paid anything for your poor life, even for a minute' is a clumsy literal rendering of 'a minute's purchase'
- c31 / gpt-6.1-sol, by opus-5.5: Loses the 'knocked me over' image and replaces it with 'gave me such a shock'
- c31 / opus-5.5, by opus-5.5: Keeps the nonstandard 'you was not aware' with no help for a B1 reader
- c31 / opus-5.5, by opus-5.5: Leaves idioms a B1 reader won't know: 'to be sure', 'I see my way now, right on', 'O'
- c31 / opus-5.5, by opus-5.5: Copies the missing opening quotation mark before 'I think your ladyship'
- c31 / opus-5.5, by opus-5.5: 'Some time ago' is a small addition not in the source
- c31 / fable-5.1, by opus-5.5: Leaves the untaught idiom 'not worth a minute's purchase' in place
- c31 / fable-5.1, by opus-5.5: ''art' keeps the dropped-h pun, which will confuse a B1 reader
- c31 / fable-5.1, by opus-5.5: 'I see my way now, right on' is left as untaught idiom
- c31 / fable-5.1, by opus-5.5: 'never wavers' is above B1 vocabulary
- c39 / opus-5.5, by opus-5.5: 'for us people with a case in the court' adds a gloss after 'suitors'
- c39 / opus-5.5, by opus-5.5: 'He has something to gain or lose in the case himself' adds an explanation of 'interested party'
- c39 / opus-5.5, by opus-5.5: 'strange attraction' adds 'strange', which is not in the source
- c39 / opus-5.5, by opus-5.5: 'I needed to get some comfort' uses the past tense where the source has the present ('I had need' means 'I need')
- c39 / fable-5.1, by opus-5.5: 'who are waiting on the court' is a gloss, and 'waiting on' is an idiom a B1 reader may not know
- c39 / fable-5.1, by opus-5.5: 'his naturally generous nature' repeats 'nature' clumsily
- c39 / fable-5.1, by opus-5.5: 'I needed to get' uses the past tense where the source has the present
- c39 / fable-5.1, by opus-5.5: 'suitors' is a hard word for B1 and is only partly explained
- c39 / gpt-6-astra, by opus-5.5: 'shocks and quarrels' is a poor rendering of 'jar and discord'
- c39 / gpt-6-astra, by opus-5.5: 'from top to bottom' is left out of the house image
- c39 / gpt-6-astra, by opus-5.5: 'a sharp pain of shame' turns the source's 'reproach' into shame
- c39 / gpt-6-astra, by opus-5.5: 'not an unkind man' weakens 'not a mean fellow'
- c39 / gpt-6.1-sol, by opus-5.5: 'it harms something good in everybody' is an interpretation added for 'taints everybody'
- c39 / gpt-6.1-sol, by opus-5.5: 'my criticism had hurt that generous part of him' is an added explanation, and it turns the source's 'as if' into a statement
- c39 / gpt-6.1-sol, by opus-5.5: 'a faint sign of that unfortunate man' is an odd, unclear phrase
- c39 / gpt-6.1-sol, by opus-5.5: 'not an unkind, selfish fellow' adds 'selfish' to 'mean'
- c47 / gpt-6.1-sol, by opus-5.5: "It is all around you here" loses the sense of "it is all over", meaning "it is finished".
- c47 / gpt-6.1-sol, by opus-5.5: It adds a sentence of the narrator's own explaining where the catechism phrase comes from, which breaks Richard's voice.
- c47 / gpt-6.1-sol, by opus-5.5: "thin and ill" adds illness that "haggard" does not state.
- c47 / gpt-6.1-sol, by opus-5.5: "in the fulness of his handsome youth" is reduced to "still young and handsome".
- c47 / opus-5.5, by opus-5.5: "catechism" is left in without explanation, which is hard for a B1 reader.
- c47 / opus-5.5, by opus-5.5: "It is all over here" is kept word for word, so its double meaning stays unclear for a B1 reader.
- c47 / opus-5.5, by opus-5.5: "I am going away on leave today" slightly changes the source's "I am away on leave this day".
- c47 / gpt-6-astra, by opus-5.5: "my officers" narrows the source's general "those put in authority over me".
- c47 / gpt-6-astra, by opus-5.5: "I cannot be free of that madness" changes the meaning of "can't be sane".
- c47 / gpt-6-astra, by opus-5.5: "watching him" is added to "unless I stayed behind him".
- c47 / fable-5.1, by opus-5.5: Old-fashioned word order is kept in "said he".
- c47 / fable-5.1, by opus-5.5: "Is nothing wrong?" is an awkward way to render "Nothing the matter?".
- c47 / fable-5.1, by opus-5.5: The idioms "smooth things over", "selling out" and "no such thing" stay in the text, which is hard for B1.
- c47 / fable-5.1, by opus-5.5: "catechism" is left without explanation.
- c63 / gpt-6.1-sol, by opus-5.5: Adds an explanatory sentence, 'These were duties about right and wrong.'
- c63 / gpt-6.1-sol, by opus-5.5: Breaking up the 'house that Jack built' chain weakens the joke of its build-up, although the repetition is still there.
- c63 / gpt-6-astra, by opus-5.5: Rewrites 'I can't be bribed' as 'No one can pay me to do something wrong', so Esther's reply 'Not by Mr. Bucket?' no longer fits.
- c63 / gpt-6-astra, by opus-5.5: Adds a gloss on 'tamed lynx': 'a wild cat, that has been trained to live with people'.
- c63 / gpt-6-astra, by opus-5.5: 'Saves us the trouble of punishing our murderers' loses the wording of 'avenges us comfortably'.
- c63 / fable-5.1, by opus-5.5: Keeps 'because I want it myself' word for word, so a B1 reader will take 'want' as 'desire' rather than 'lack'.
- c63 / fable-5.1, by opus-5.5: Adds glosses: 'leave him unable to act' and 'the one who understands these things'.
- c63 / fable-5.1, by opus-5.5: Leaves 'tamed lynx' unexplained, and keeps the very long chain sentences that are hard for a B1 reader to parse.
- c63 / opus-5.5, by opus-5.5: Keeps 'because I want it myself', which a B1 reader will misread as desire rather than lack.
- c63 / opus-5.5, by opus-5.5: Adds a definition: 'a bribe, that is, money given to make someone do wrong'.
- c63 / opus-5.5, by opus-5.5: Adds glosses: 'a kind of wild cat' and 'Prejudices, or unfair fixed opinions'.
- c63 / opus-5.5, by opus-5.5: Moves the narrator's exclamation ('Surely nobody else...') to the end of the paragraph and makes it weaker.
- c55 / gpt-6.1-sol, by opus-5.5: The hedge in 'I cannot say but that he may have been followed' is dropped and it becomes a plain 'He may have been followed'.
- c55 / gpt-6.1-sol, by opus-5.5: 'This crime was most horrible and showed a shocking lack of fear' cuts the crime off from the ceremony sentence, so the link between the two is weakened.
- c55 / gpt-6-astra, by opus-5.5: The hedge in 'I cannot say but that' is dropped.
- c55 / gpt-6-astra, by opus-5.5: 'glances at him' becomes 'watches him closely', which changes the action.
- c55 / gpt-6-astra, by opus-5.5: 'charming towards women' is a looser rendering of 'natural gallantry'.
- c55 / fable-5.1, by opus-5.5: The gloss 'accomplices—people who helped him—' is an added explanation.
- c55 / fable-5.1, by opus-5.5: 'weak, tired cousin': 'tired' is an addition.
- c55 / fable-5.1, by opus-5.5: The cousin's clipped, fragmentary speech is turned into full normal sentences, so his voice is lost.
- c55 / fable-5.1, by opus-5.5: Hard or idiomatic wording is kept for B1: 'kept myself on this case', 'everything that has been traced', 'at the present moment', 'bring ... to light'.
- c55 / opus-5.5, by opus-5.5: 'made people think he was richer than he was' invents the claim that he was not rich.
- c55 / opus-5.5, by opus-5.5: 'I will fail to stay loyal' changes the meaning of 'fail in the assertion of my fidelity', which means failing to show loyalty.
- c55 / opus-5.5, by opus-5.5: 'protest' is the wrong word for 'protestation'.
- c55 / opus-5.5, by opus-5.5: The gloss 'a cocked hat, a three-cornered hat' is an added explanation.
- c55 / opus-5.5, by opus-5.5: 'weak, feeble cousin' is a redundant doubling.
- c55 / opus-5.5, by opus-5.5: 'bring into the light' is an idiom left in for B1.
- c15 / opus-5.5, by fable-5.1: 'they are most remarkable men' — present tense for two dead husbands
- c15 / opus-5.5, by fable-5.1: 'above all others' is a loose rendering of 'pre-eminently'
- c15 / opus-5.5, by fable-5.1: 'elegant and fashionable dinner' adds 'fashionable'
- c15 / opus-5.5, by fable-5.1: 'claret, a kind of red wine' — explanatory gloss added
- c15 / fable-5.1, by fable-5.1: 'a very elegant and polite meal' — 'polite' is a wrong word for 'genteel'
- c15 / fable-5.1, by fable-5.1: 'that Captain Swosser so very much was' — awkward, hard-to-parse rendering of 'pre-eminently'
- c15 / fable-5.1, by fable-5.1: 'would have liked to meet' shifts 'to have seen'
- c15 / fable-5.1, by fable-5.1: 'ordinary glass' adds 'ordinary'
- c15 / fable-5.1, by fable-5.1: 'claret, a kind of red wine' — explanatory gloss added
- c15 / gpt-6-astra, by fable-5.1: 'said Mr. Badger confidently' — mistranslates 'in a tone of confidence' (confidential tone)
- c15 / gpt-6-astra, by fable-5.1: 'the Professor's drinking cup, James—the one with the stem!' — invented description in Badger's speech
- c15 / gpt-6-astra, by fable-5.1: 'as to compare myself with such excellent men. I could not claim to be...' — padded into two sentences, partly invented
- c15 / gpt-6-astra, by fable-5.1: 'I think' for 'I feel'; 'myself' added to 'I am quite a Sailor'
- c15 / gpt-6-astra, by fable-5.1: 'very special and unusual wine' pads 'very curious'
- c15 / gpt-6-astra, by fable-5.1: 'claret, a kind of red wine' — explanatory gloss added
- c15 / gpt-6.1-sol, by fable-5.1: 'said Mr. Badger confidently' — mistranslates 'in a tone of confidence'
- c15 / gpt-6.1-sol, by fable-5.1: 'So we heard all about them' loses the ironic 'full benefit of them'
- c15 / gpt-6.1-sol, by fable-5.1: 'the Professor's cup with a stem' — clumsy gloss put into Badger's mouth
- c15 / gpt-6.1-sol, by fable-5.1: 'They were men of the very highest quality' — added sentence
- c15 / gpt-6.1-sol, by fable-5.1: 'claret, a red wine' — explanatory gloss added
- c7 / fable-5.1, by fable-5.1: 'how soft and fine it feels' adds 'soft', not in source
- c7 / fable-5.1, by fable-5.1: 'sits as judge in the Inn' adds an explanation
- c7 / fable-5.1, by fable-5.1: 'All's fish that comes to my net' image dropped for 'I take anything that comes my way'
- c7 / fable-5.1, by fable-5.1: 'christening' image dropped for plain 'a name'
- c7 / gpt-6-astra, by fable-5.1: 'Usually, the lady's attention wandered from one thing to another' is an added explanatory sentence
- c7 / gpt-6-astra, by fable-5.1: 'documents written on animal skin' glosses parchment in-text
- c7 / gpt-6-astra, by fable-5.1: 'Aye, aye!' flattened to 'Yes, yes!'
- c7 / gpt-6-astra, by fable-5.1: 'noble' lost in 'that great and learned man'
- c7 / opus-5.5, by fable-5.1: 'her room' (singular) for 'her apartment'
- c7 / opus-5.5, by fable-5.1: 'All's fish that comes to my net' image dropped for 'I take anything that comes my way'
- c7 / opus-5.5, by fable-5.1: 'parchmentses', 'He don't', 'pretty well every day' left as untaught dialect/idiom for a B1 reader
- c7 / gpt-6.1-sol, by fable-5.1: 'Usually, the old lady's attention wandered from one thing to another' is an added explanatory sentence
- c7 / gpt-6.1-sol, by fable-5.1: 'documents on animal skin' glosses parchment in-text
- c7 / gpt-6.1-sol, by fable-5.1: 'everything that comes into my net is useful to me' shifts the proverb's sense
- c7 / gpt-6.1-sol, by fable-5.1: 'that great lord with all his learning' is an awkward, slightly off rendering of 'noble and learned brother'
- c23 / gpt-6.1-sol, by fable-5.1: 'ruins like those of the Druids, ancient priests' adds an explanation and leaves unclear that the ruins are the bread and butter
- c23 / gpt-6.1-sol, by fable-5.1: 'spurs, the metal points riders wear on their boots' is an added gloss
- c23 / gpt-6.1-sol, by fable-5.1: 'The tea is like a tide flowing out' loses the specific ebbtide image of the tea going down in the basin
- c23 / fable-5.1, by fable-5.1: 'so fast that' is a small interpretive addition to 'so disperses … that'
- c23 / fable-5.1, by fable-5.1: 'the circulation, the flow of my blood' inserts a gloss into Grandfather Smallweed's dialogue
- c23 / fable-5.1, by fable-5.1: 'a trooper, a soldier on horseback' adds an explanatory apposition
- c23 / opus-5.5, by fable-5.1: 'harder to agree with Miss Smallweed's opinions' mistranslates 'meeting her views' (satisfying/complying with them)
- c23 / opus-5.5, by fable-5.1: 'His step … is slow' invents 'slow' for 'measured'
- c23 / opus-5.5, by fable-5.1: 'Druidical ruins' left in quotation marks with no help for a B1 reader
- c23 / opus-5.5, by fable-5.1: 'short and stiff' is a doubtful rendering of 'crisp' hair
- c23 / gpt-6-astra, by fable-5.1: 'These are the metal points riders wear on their boots to urge horses on' is an invented explanatory sentence
- c23 / gpt-6-astra, by fable-5.1: 'ruins like those left by the Druids, ancient priests' adds an explanation and leaves the ruins unidentified
- c23 / gpt-6-astra, by fable-5.1: 'a knock at the door saves her from this' adds an interpretation not in the source
- c23 / gpt-6-astra, by fable-5.1: 'take the whole family into his own body' is a clumsy literalisation of 'absorb into himself'
- c23 / gpt-6-astra, by fable-5.1: 'the honour of meeting' for 'seeing'
- c31 / opus-5.5, by fable-5.1: Keeps Guppy's ungrammatical 'you was not aware of me' unexplained – a B1 reader may take it as correct English
- c31 / opus-5.5, by fable-5.1: 'I don't know' left hanging before a separate question – slightly awkward restructuring
- c31 / fable-5.1, by fable-5.1: 'would not have been worth a minute's purchase' left untranslated – untaught idiom for a B1 reader
- c31 / fable-5.1, by fable-5.1: 'printed on my 'art' – dialect spelling likely to puzzle a B1 reader
- c31 / fable-5.1, by fable-5.1: 'never wavers' and 'within call' are above B1 level
- c31 / gpt-6.1-sol, by fable-5.1: 'damn it' for Guppy's euphemistic 'dash it' – wrong register
- c31 / gpt-6.1-sol, by fable-5.1: Drops 'I am sure' from the apology to the love-birds
- c31 / gpt-6.1-sol, by fable-5.1: 'no one would have paid anything for your poor life, even for a minute' – unclear rendering of the idiom
- c31 / gpt-6.1-sol, by fable-5.1: 'It gave me such a shock' loses the 'knocked me over' image
- c31 / gpt-6-astra, by fable-5.1: 'damn it' for 'dash it' – wrong register
- c31 / gpt-6-astra, by fable-5.1: Drops 'I am sure' from the apology to the love-birds
- c31 / gpt-6-astra, by fable-5.1: 'Perhaps your ladyship' for 'I think your ladyship' – changes Guppy's phrasing
- c31 / gpt-6-astra, by fable-5.1: Repeatedly replaces 'your ladyship' with 'you', flattening Guppy's obsequious voice
- c31 / gpt-6-astra, by fable-5.1: 'You really do look even more surprisingly like her than I thought' – clumsy, unclear sentence
- c39 / gpt-6-astra, by fable-5.1: 'shocks and quarrels' is an odd rendering of 'jar and discord'
- c39 / gpt-6-astra, by fable-5.1: Nature made neuter ('It') and the sentence split loses the single image of the wakeful night
- c39 / gpt-6-astra, by fable-5.1: 'a sharp pain of shame' narrows 'a pang of reproach'
- c39 / gpt-6-astra, by fable-5.1: 'I certainly need' shifts 'I had need' to the present
- c39 / fable-5.1, by fable-5.1: 'who are waiting on the court' is an added gloss on 'suitors'
- c39 / fable-5.1, by fable-5.1: 'his naturally generous nature' is clumsy doubling
- c39 / fable-5.1, by fable-5.1: 'I needed to get' slightly mistimes 'I had need to get'
- c39 / gpt-6.1-sol, by fable-5.1: 'my criticism had hurt that generous part of him' fixes an interpretation on 'felt a pang of reproach'
- c39 / gpt-6.1-sol, by fable-5.1: 'changed me a little for the worse' drops the 'twisted' image
- c39 / gpt-6.1-sol, by fable-5.1: 'harms something good in everybody' flattens 'taints everybody'
- c39 / gpt-6.1-sol, by fable-5.1: 'faint sign' weakens 'a shade of that unfortunate man'
- c39 / gpt-6.1-sol, by fable-5.1: 'and still say such things' is a small addition to the remonstrance
- c39 / opus-5.5, by fable-5.1: 'strange attraction' adds 'strange'
- c39 / opus-5.5, by fable-5.1: 'for us people with a case in the court' is an added gloss on 'suitors'
- c39 / opus-5.5, by fable-5.1: 'He has something to gain or lose in the case himself' is an added gloss on 'interested party'
- c39 / opus-5.5, by fable-5.1: 'It was not I' tacked on at the end reads awkwardly
- c47 / fable-5.1, by fable-5.1: 'smooth things over' and 'selling out' are idioms left in for a B1 reader, only partly glossed
- c47 / fable-5.1, by fable-5.1: 'Is nothing wrong?' is an unnatural rendering of 'Nothing the matter?'
- c47 / fable-5.1, by fable-5.1: 'catechism' left unexplained for a B1 reader
- c47 / gpt-6-astra, by fable-5.1: 'I cannot be free of that madness' shifts 'can't be sane'
- c47 / gpt-6-astra, by fable-5.1: 'watching him' added to 'at his back'
- c47 / gpt-6-astra, by fable-5.1: 'I thought arguing would... So I thought it best not to argue' is a clumsy, repetitive rendering of the mood sentence
- c47 / opus-5.5, by fable-5.1: 'Call it madness, if you like' adds words not in the source
- c47 / opus-5.5, by fable-5.1: 'I know that thing too well' loosens 'with my experience of that thing'
- c47 / opus-5.5, by fable-5.1: 'thin, worried face' pads out 'haggard'
- c47 / opus-5.5, by fable-5.1: 'catechism' left unexplained for a B1 reader
- c47 / gpt-6.1-sol, by fable-5.1: Adds an explanatory sentence about the catechism phrase, breaking Richard's speech
- c47 / gpt-6.1-sol, by fable-5.1: 'How tired, thin and ill he looked' adds 'ill'
- c47 / gpt-6.1-sol, by fable-5.1: 'making my sale of my position as an officer seem less unpleasant' is awkward and hard to parse
- c47 / gpt-6.1-sol, by fable-5.1: 'I care about only one thing. All my thoughts...' flattens the 'no care, no mind, no heart, no soul' rhythm
- c47 / gpt-6.1-sol, by fable-5.1: 'You can read it in everything in this room. It is all around you here' loosens the source line
- c55 / fable-5.1, by fable-5.1: 'cocked hat' left unglossed for a B1 reader
- c55 / fable-5.1, by fable-5.1: 'accomplices—people who helped him' adds a small explanatory gloss
- c55 / fable-5.1, by fable-5.1: 'weak, tired cousin' — 'tired' is not quite 'debilitated'
- c55 / opus-5.5, by fable-5.1: 'He makes this protest' — 'protestation' means solemn declaration, not protest
- c55 / opus-5.5, by fable-5.1: 'some fellow will be hanged' — source says 'executed'
- c55 / opus-5.5, by fable-5.1: 'weak, feeble cousin' is redundant
- c55 / opus-5.5, by fable-5.1: 'a cocked hat, a three-cornered hat' adds a gloss
- c55 / gpt-6-astra, by fable-5.1: 'I cannot say but that' hedge dropped before 'He may have been followed'
- c55 / gpt-6-astra, by fable-5.1: 'everything we have discovered' adds 'we'
- c55 / gpt-6-astra, by fable-5.1: 'I shall feel this until this crime is solved' restructures and slightly flattens the declaration
- c55 / gpt-6.1-sol, by fable-5.1: 'showed a shocking lack of fear' is an awkward, off rendering of 'audacious'
- c55 / gpt-6.1-sol, by fable-5.1: 'chosen as a victim' drops 'first marked'
- c55 / gpt-6.1-sol, by fable-5.1: Splits 'the shock I have received from this crime' so the shock is no longer tied to the crime
- c63 / gpt-6-astra, by fable-5.1: 'I can't be bribed' becomes 'No one can pay me to do something wrong', so Esther's reply 'Not by Mr. Bucket?' no longer fits grammatically
- c63 / gpt-6-astra, by fable-5.1: Lynx glossed with an added explanation ('a wild cat, that has been trained to live with people')
- c63 / gpt-6-astra, by fable-5.1: 'avenges us comfortably when we are murdered' reinterpreted as 'saves us the trouble of punishing our murderers'
- c63 / gpt-6-astra, by fable-5.1: House-that-Jack-built chain chopped into 'That is the boy...' fragments, losing the cumulative form
- c63 / gpt-6-astra, by fable-5.1: 'disregard of several moral obligations' muddled into 'ignored several duties to do what was right'
- c63 / gpt-6.1-sol, by fable-5.1: Invented explanatory sentence 'These were duties about right and wrong.'
- c63 / gpt-6.1-sol, by fable-5.1: Narrator's charge loses the word 'bribe' ('broken that trust for money'), though Skimpole then answers 'I can't be bribed'
- c63 / gpt-6.1-sol, by fable-5.1: Cumulative Jack-built chain broken into separate repeated sentences, weakening the joke
- c63 / gpt-6.1-sol, by fable-5.1: 'expressly' softened to 'clearly'
- c63 / opus-5.5, by fable-5.1: Added gloss 'that is, money given to make someone do wrong'
- c63 / opus-5.5, by fable-5.1: Added gloss 'calmly and wisely' after 'act with philosophy'
- c63 / opus-5.5, by fable-5.1: Added gloss 'or unfair fixed opinions' for prejudices
- c63 / opus-5.5, by fable-5.1: Added gloss 'a kind of wild cat' for lynx
- c63 / opus-5.5, by fable-5.1: 'because I want it myself' kept verbatim; B1 reader will read 'want' as desire, not lack
- c63 / fable-5.1, by fable-5.1: Added gloss 'leave him unable to act' after 'paralyse'
- c63 / fable-5.1, by fable-5.1: Added gloss 'the one who understands these things' after 'the knowing man'
- c63 / fable-5.1, by fable-5.1: 'like a philosopher' is a small addition to 'act with philosophy'
- c63 / fable-5.1, by fable-5.1: 'because I want it myself' kept verbatim; 'want' = lack is untaught for B1
- c63 / fable-5.1, by fable-5.1: 'expressly', 'essential' sit above everyday B1 vocabulary
- c7 / fable-5.1, by gpt-6.1-sol: Adds softness to Krook's praise of Ada's hair.
- c7 / fable-5.1, by gpt-6.1-sol: Drops the christening image when explaining the nicknames.
- c7 / fable-5.1, by gpt-6.1-sol: Drops the fish-and-net image.
- c7 / fable-5.1, by gpt-6.1-sol: Adds 'as judge' to explain 'sits in the Inn'.
- c7 / fable-5.1, by gpt-6.1-sol: Leaves 'taking such a freedom' insufficiently clear for B1.
- c7 / gpt-6.1-sol, by gpt-6.1-sol: Weakens the lady's insistently pressing entreaties to strange eagerness.
- c7 / gpt-6.1-sol, by gpt-6.1-sol: Changes 'I assure you' into 'I promise you'.
- c7 / gpt-6.1-sol, by gpt-6.1-sol: Strengthens the old lady's momentarily fixed attention into inability to look away.
- c7 / gpt-6.1-sol, by gpt-6.1-sol: Adds a separate explanation of the old lady's usually wandering attention.
- c7 / gpt-6.1-sol, by gpt-6.1-sol: Drops the christening image.
- c7 / gpt-6.1-sol, by gpt-6.1-sol: Adds an explanation of parchment as documents on animal skin.
- c7 / gpt-6.1-sol, by gpt-6.1-sol: Drops the fish from the fish-and-net image.
- c7 / gpt-6.1-sol, by gpt-6.1-sol: Adds 'holds court' to explain 'sits in the Inn'.
- c7 / gpt-6.1-sol, by gpt-6.1-sol: Leaves 'digging away in a muddle' difficult for B1.
- c7 / opus-5.5, by gpt-6.1-sol: Adds an explanatory gloss in 'good sign, or omen'.
- c7 / opus-5.5, by gpt-6.1-sol: Adds seriousness to the old lady's stately manner.
- c7 / opus-5.5, by gpt-6.1-sol: Weakens Richard's rebuke to 'You don't need to touch it so freely'.
- c7 / opus-5.5, by gpt-6.1-sol: Adds an explanatory comparison in 'as if at a christening'.
- c7 / opus-5.5, by gpt-6.1-sol: Drops the fish-and-net image.
- c7 / opus-5.5, by gpt-6.1-sol: Retains the difficult dialect word 'parchmentses'.
- c7 / opus-5.5, by gpt-6.1-sol: Leaves 'pretty well every day' and 'digging away in a muddle' insufficiently accessible for B1.
- c7 / gpt-6-astra, by gpt-6.1-sol: Changes 'I assure you' into 'I promise you'.
- c7 / gpt-6-astra, by gpt-6.1-sol: Strengthens the old lady's momentarily fixed attention into inability to look away.
- c7 / gpt-6-astra, by gpt-6.1-sol: Adds a separate explanation of the old lady's usually wandering attention.
- c7 / gpt-6-astra, by gpt-6.1-sol: Makes Krook's return to his former self uncertain by adding 'seemed'.
- c7 / gpt-6-astra, by gpt-6.1-sol: Drops the christening image.
- c7 / gpt-6-astra, by gpt-6.1-sol: Adds an explanation of parchment as documents written on animal skin.
- c7 / gpt-6-astra, by gpt-6.1-sol: Changes the inclusive collecting metaphor into a statement welcoming actual fish.
- c7 / gpt-6-astra, by gpt-6.1-sol: Adds 'holds court' to explain 'sits in the Inn'.
- c7 / gpt-6-astra, by gpt-6.1-sol: Weakens the mock-formal 'noble and learned brother' to 'brother, that great and learned man'.
- c15 / fable-5.1, by gpt-6.1-sol: Changes wanting to have seen Captain Swosser into wanting to have met him.
- c15 / fable-5.1, by gpt-6.1-sol: Reduces the vivid 'speaking likeness' to exact resemblance.
- c15 / fable-5.1, by gpt-6.1-sol: Adds 'ordinary' to the rejected glass.
- c15 / fable-5.1, by gpt-6.1-sol: Adds an explanation of claret.
- c15 / fable-5.1, by gpt-6.1-sol: Leaves 'goblet' and 'the full benefit of them' difficult for an independent B1 reader.
- c15 / fable-5.1, by gpt-6.1-sol: Leaves the elliptical toast 'your health' unsimplified.
- c15 / gpt-6-astra, by gpt-6.1-sol: Adds 'enjoyed', making the narrator's ironic 'full benefit' sound more positively pleasurable.
- c15 / gpt-6-astra, by gpt-6.1-sol: Adds an explanation of claret.
- c15 / gpt-6-astra, by gpt-6.1-sol: Adds 'special' to the description of how the wine will taste.
- c15 / gpt-6.1-sol, by gpt-6.1-sol: Adds an explicit joint decision in 'we chose the same day'.
- c15 / gpt-6.1-sol, by gpt-6.1-sol: Replaces the ironic 'full benefit of them' with the neutral 'heard all about them'.
- c15 / gpt-6.1-sol, by gpt-6.1-sol: Leaves 'African Station' unexplained and potentially misleading for a B1 reader.
- c15 / gpt-6.1-sol, by gpt-6.1-sol: Retains the difficult construction 'a man I should like to have seen'.
- c15 / gpt-6.1-sol, by gpt-6.1-sol: Adds an explanation of claret.
- c15 / opus-5.5, by gpt-6.1-sol: Repeatedly substitutes importance for distinction.
- c15 / opus-5.5, by gpt-6.1-sol: Adds 'above all others', turning exceptional quality into an absolute ranking.
- c15 / opus-5.5, by gpt-6.1-sol: Reduces the vivid 'speaking likeness' to exact resemblance.
- c15 / opus-5.5, by gpt-6.1-sol: Adds 'fashionable' to the description of dinner.
- c15 / opus-5.5, by gpt-6.1-sol: Adds an explanation of claret.
- c15 / opus-5.5, by gpt-6.1-sol: Leaves 'African Station' unexplained and potentially misleading for a B1 reader.
- c15 / opus-5.5, by gpt-6.1-sol: Retains the difficult construction 'a man I should like to have seen'.
- c15 / opus-5.5, by gpt-6.1-sol: Leaves 'in his head', 'the full benefit of them', and 'goblet' insufficiently accessible.
- c15 / opus-5.5, by gpt-6.1-sol: Leaves the elliptical toast 'your health' unsimplified.
- c23 / opus-5.5, by gpt-6.1-sol: Changes satisfying Miss Smallweed's expectations into agreeing with her opinions.
- c23 / opus-5.5, by gpt-6.1-sol: Adds shortness to Mr. George's hair and replaces its crisp texture with stiffness.
- c23 / opus-5.5, by gpt-6.1-sol: Adds slowness to Mr. George's measured, heavy step.
- c23 / opus-5.5, by gpt-6.1-sol: Specifies a uniform and military equipment where the source leaves the discarded clothing and equipment unspecified.
- c23 / opus-5.5, by gpt-6.1-sol: Adds an explanatory definition after 'trooper'.
- c23 / opus-5.5, by gpt-6.1-sol: Leaves 'How de do', 'ha'n't', and ''em' unexplained for the B1 reader.
- c23 / gpt-6.1-sol, by gpt-6.1-sol: Adds the explanation that Druids were ancient priests.
- c23 / gpt-6.1-sol, by gpt-6.1-sol: Adds an explanatory description of spurs.
- c23 / gpt-6.1-sol, by gpt-6.1-sol: Changes the neutral 'Middling' to the somewhat more positive 'Fairly well'.
- c23 / gpt-6-astra, by gpt-6.1-sol: Adds the explanation that Druids were ancient priests.
- c23 / gpt-6-astra, by gpt-6.1-sol: Adds an explanation of spurs and their purpose.
- c23 / gpt-6-astra, by gpt-6.1-sol: Changes the neutral 'Middling' to the somewhat more positive 'Fairly well'.
- c23 / gpt-6-astra, by gpt-6.1-sol: Drops the explicitly muscular quality of Mr. George's hands.
- c23 / gpt-6-astra, by gpt-6.1-sol: Drops the explicit smallness of the Smallweeds' bodies.
- c23 / gpt-6-astra, by gpt-6.1-sol: Weakens the conditional image of absorbing the household from 'would' to 'might'.
- c23 / fable-5.1, by gpt-6.1-sol: Identifies the Druidical ruins as bread and butter without support in this passage.
- c23 / fable-5.1, by gpt-6.1-sol: Invents speed as the reason for Miss Smallweed's rebuke.
- c23 / fable-5.1, by gpt-6.1-sol: Adds shortness to Mr. George's hair.
- c23 / fable-5.1, by gpt-6.1-sol: Specifies a uniform where the source leaves the discarded clothing unspecified.
- c23 / fable-5.1, by gpt-6.1-sol: Says he stresses the 'last word', although the source specifies the last adjective, 'devilish'.
- c23 / fable-5.1, by gpt-6.1-sol: Adds explanatory definitions of 'trooper' and 'circulation'.
- c23 / fable-5.1, by gpt-6.1-sol: Leaves 'Druid-like', 'oyster-knife', 'pinched ways', and several dialect forms unexplained for the B1 reader.
- c31 / gpt-6.1-sol, by gpt-6.1-sol: “Damn it” and “Damn these notes” strengthen Guppy's mild “dash” into stronger swearing.
- c31 / gpt-6.1-sol, by gpt-6.1-sol: “No one would have paid anything” muddles the narrator's threat that Guppy would scarcely survive another minute.
- c31 / gpt-6.1-sol, by gpt-6.1-sol: “Put myself entirely in your ladyship's hands” remains an unexplained idiom.
- c31 / gpt-6-astra, by gpt-6.1-sol: “A few points” changes the stated “one or two.”
- c31 / gpt-6-astra, by gpt-6.1-sol: “Perhaps your ladyship” weakens Guppy's assertion, “I think your ladyship.”
- c31 / gpt-6-astra, by gpt-6.1-sol: “Damn it” and “Damn these notes” strengthen the original mild swearing.
- c31 / gpt-6-astra, by gpt-6.1-sol: The warning about Guppy's safety drops the original image of his life's purchase value.
- c31 / gpt-6-astra, by gpt-6.1-sol: “Knocked me over,” “in your ladyship's hands,” and “I dare say” remain unexplained idioms.
- c31 / fable-5.1, by gpt-6.1-sol: “My 'art” leaves the meaning of “heart” inaccessible to an independent B1 reader.
- c31 / fable-5.1, by gpt-6.1-sol: “Would not have been worth a minute's purchase” retains the original difficult idiom without making its meaning accessible.
- c31 / fable-5.1, by gpt-6.1-sol: “Dash it,” “taken the liberty,” “within call,” and “I see my way” retain difficult expressions.
- c31 / fable-5.1, by gpt-6.1-sol: “Did your ladyship notice that” slightly presupposes the resemblance that Guppy originally asks her to consider.
- c31 / opus-5.5, by gpt-6.1-sol: “Castles” loses the defensive force of “strongholds.”
- c31 / opus-5.5, by gpt-6.1-sol: The extra sentence about living another minute explains the narrator's image instead of simply recasting it.
- c31 / opus-5.5, by gpt-6.1-sol: “You was” retains nonstandard grammar without helping the learner interpret it.
- c31 / opus-5.5, by gpt-6.1-sol: “Dash it,” “knocked me over,” “I dare say,” and “I see my way” remain unexplained expressions.
- c47 / gpt-6-astra, by gpt-6.1-sol: Adds an explanation of the catechism while also retaining its quoted wording.
- c47 / gpt-6-astra, by gpt-6.1-sol: Adds 'watching him' to explain the image of being at Vholes's back.
- c47 / opus-5.5, by gpt-6.1-sol: 'Full strength of his youth' introduces physical strength where the source describes youth in its fullness.
- c47 / opus-5.5, by gpt-6.1-sol: Leaves 'catechism' and 'right there behind him' insufficiently accessible for an independent B1 reader.
- c47 / fable-5.1, by gpt-6.1-sol: 'Worn and tired' loses the visibly gaunt appearance conveyed by 'haggard.'
- c47 / fable-5.1, by gpt-6.1-sol: 'Full strength' introduces physical strength absent from the source.
- c47 / fable-5.1, by gpt-6.1-sol: Replaces selling his officer's position with merely giving up his place in the army.
- c47 / fable-5.1, by gpt-6.1-sol: Adds an explanatory gloss after 'selling out' while leaving 'smooth things over' unexplained.
- c47 / fable-5.1, by gpt-6.1-sol: Leaves 'catechism' and 'right there behind him' insufficiently accessible for an independent B1 reader.
- c47 / gpt-6.1-sol, by gpt-6.1-sol: Adds that Richard looks ill, which the source does not state.
- c47 / gpt-6.1-sol, by gpt-6.1-sol: Loses the emphasis on Richard being in the fullness of his youth.
- c47 / gpt-6.1-sol, by gpt-6.1-sol: Adds a separate explanatory sentence identifying the religious source of the authority phrase.
- c39 / fable-5.1, by gpt-6.1-sol: Adds an explanatory gloss to 'suitors': 'who are waiting on the court.'
- c39 / fable-5.1, by gpt-6.1-sol: 'I needed' shifts Richard's current need for comfort into the past.
- c39 / gpt-6.1-sol, by gpt-6.1-sol: 'Making any firm decision' narrows 'doing anything very definite' from action to decision.
- c39 / gpt-6.1-sol, by gpt-6.1-sol: 'Changed me a little for the worse' drops the image of being twisted.
- c39 / gpt-6.1-sol, by gpt-6.1-sol: 'Harms something good in everybody' replaces the image of contamination with an explanation.
- c39 / opus-5.5, by gpt-6.1-sol: 'All night' adds a duration the source does not specify.
- c39 / opus-5.5, by gpt-6.1-sol: Adds 'strange' to the attraction.
- c39 / opus-5.5, by gpt-6.1-sol: Adds explanatory glosses for 'suitors' and 'interested party.'
- c39 / opus-5.5, by gpt-6.1-sol: 'Whisper' specifies a manner of speaking absent from the source.
- c39 / opus-5.5, by gpt-6.1-sol: 'I needed' shifts Richard's current need for comfort into the past.
- c39 / gpt-6-astra, by gpt-6.1-sol: 'Shocks' misrepresents the discord conveyed by 'jar.'
- c39 / gpt-6-astra, by gpt-6.1-sol: 'Making any firm plans' narrows 'doing anything very definite.'
- c39 / gpt-6-astra, by gpt-6.1-sol: Drops 'from top to bottom' from the house image.
- c39 / gpt-6-astra, by gpt-6.1-sol: 'Most of what I have to say' changes the central subject into a proportion of the conversation.
- c39 / gpt-6-astra, by gpt-6.1-sol: 'Whisper' specifies a manner of speaking absent from the source.
- c39 / gpt-6-astra, by gpt-6.1-sol: 'Unkind' loses the selfish or ungenerous sense of 'mean.'
- c39 / gpt-6-astra, by gpt-6.1-sol: 'Should not be so ready to suspect' adds readiness rather than describing suspicion and distrust as poor qualities.
- c55 / opus-5.5, by gpt-6.1-sol: “Often” weakens “constantly” sitting at his table.
- c55 / opus-5.5, by gpt-6.1-sol: “Richer than he was” invents a comparison with his actual wealth.
- c55 / opus-5.5, by gpt-6.1-sol: “A three-cornered hat” adds an explanatory gloss.
- c55 / opus-5.5, by gpt-6.1-sol: The cousin’s first reference to execution becomes specifically hanging.
- c55 / opus-5.5, by gpt-6.1-sol: “Ain’t” and “bring into the light” leave difficult language unsimplified.
- c55 / gpt-6.1-sol, by gpt-6.1-sol: “Often” weakens “constantly” sitting at his table.
- c55 / gpt-6.1-sol, by gpt-6.1-sol: “Most trusted” shifts “trustiest” from trustworthiness to others’ trust.
- c55 / gpt-6-astra, by gpt-6.1-sol: “Often” weakens “constantly” sitting at his table.
- c55 / gpt-6-astra, by gpt-6.1-sol: Bucket watching him closely replaces a glance with sustained observation.
- c55 / fable-5.1, by gpt-6.1-sol: “Shameless” loses the daring conveyed by “audacious”.
- c55 / fable-5.1, by gpt-6.1-sol: “People who helped him” adds an explanatory gloss.
- c55 / fable-5.1, by gpt-6.1-sol: “Tired” adds a condition not specified by “debilitated”.
- c55 / fable-5.1, by gpt-6.1-sol: The cousin’s complete sentences reduce the original’s fragmented voice.
- c55 / fable-5.1, by gpt-6.1-sol: “Cocked hat”, “ain’t” and “bring ... to light” remain difficult for an independent B1 reader.
- c63 / opus-5.5, by gpt-6.1-sol: Adds an explicit definition of a bribe.
- c63 / opus-5.5, by gpt-6.1-sol: Adds explanatory glosses for philosophy, prejudices and lynx.
- c63 / opus-5.5, by gpt-6.1-sol: Leaves 'because I want it myself' ambiguous: here 'want' means lack the faith, not desire it.
- c63 / opus-5.5, by gpt-6.1-sol: Adds 'in the world' to the claim about holding things together.
- c63 / gpt-6.1-sol, by gpt-6.1-sol: Narrows 'moral obligations' to 'duties to others'.
- c63 / gpt-6.1-sol, by gpt-6.1-sol: Breaking the cumulative nursery-rhyme sentences into separate statements weakens the repeated image and comic rhythm.
- c63 / fable-5.1, by gpt-6.1-sol: Changes specially directed energy into 'a very special kind of energy'.
- c63 / fable-5.1, by gpt-6.1-sol: Leaves 'because I want it myself' ambiguous: here 'want' means lack the faith, not desire it.
- c63 / fable-5.1, by gpt-6.1-sol: Adds explanatory glosses for 'paralyse' and 'the knowing man'.
- c63 / fable-5.1, by gpt-6.1-sol: Adds 'calmly and wisely' as an interpretation of acting with philosophy.
- c63 / gpt-6-astra, by gpt-6.1-sol: Replacing 'I can't be bribed' makes the following 'Not by Mr. Bucket?' grammatically disconnected.
- c63 / gpt-6-astra, by gpt-6.1-sol: Changes being above suspicion into being beyond any reason for doubt.
- c63 / gpt-6-astra, by gpt-6.1-sol: Adds a definition of lynx and an explanation of its being tamed.
- c63 / gpt-6-astra, by gpt-6.1-sol: Changes comfortable revenge into saving the victims the trouble of punishing their murderers.
- c63 / gpt-6-astra, by gpt-6.1-sol: Narrows the next 'detective operation' to investigating a crime.
- c63 / gpt-6-astra, by gpt-6.1-sol: Breaking the cumulative nursery-rhyme sentences weakens their comic rhythm.
- c15 / fable-5.1, by gpt-6-astra: Changes Mr. Badger's confident tone into the sharing of private information.
- c15 / fable-5.1, by gpt-6-astra: Changes wanting to have seen Captain Swosser into wanting to have met him.
- c15 / fable-5.1, by gpt-6-astra: Calls the meal 'polite', an awkward and inaccurate rendering of 'genteel'.
- c15 / fable-5.1, by gpt-6-astra: Adds an explanation identifying claret as red wine.
- c15 / fable-5.1, by gpt-6-astra: Leaves 'goblet', 'first-rate' and 'your health' insufficiently accessible for an independent B1 reader.
- c15 / gpt-6-astra, by gpt-6-astra: Adds an explanation identifying claret as red wine.
- c15 / gpt-6-astra, by gpt-6-astra: Turns the description implicit in 'goblet' into an added instruction to James: 'the one with the stem'.
- c15 / opus-5.5, by gpt-6-astra: Changes Mr. Badger's confident tone into the telling of a secret.
- c15 / opus-5.5, by gpt-6-astra: Adds 'above all others', making Swosser superior to everyone rather than an outstanding example.
- c15 / opus-5.5, by gpt-6-astra: Adds 'fashionable' to the description of the dinner.
- c15 / opus-5.5, by gpt-6-astra: Adds an explanation identifying claret as red wine.
- c15 / opus-5.5, by gpt-6-astra: Leaves 'African Station', 'goblet', 'your health' and 'I should like to have seen' insufficiently accessible for B1.
- c15 / gpt-6.1-sol, by gpt-6-astra: Replaces the narrator's ironic 'full benefit' with the flatter 'heard all about them'.
- c15 / gpt-6.1-sol, by gpt-6-astra: Adds an explanation identifying claret as red wine.
- c15 / gpt-6.1-sol, by gpt-6-astra: Leaves 'African Station' and 'I should like to have seen' insufficiently accessible for B1.
- c7 / gpt-6.1-sol, by gpt-6-astra: “Unable to look away” strengthens the claim that Ada briefly holds the old lady's wandering attention.
- c7 / gpt-6.1-sol, by gpt-6-astra: The separate sentence beginning “Usually” adds an explanatory generalization.
- c7 / gpt-6.1-sol, by gpt-6-astra: “Given ... these names” drops the christening image.
- c7 / gpt-6.1-sol, by gpt-6-astra: “Everything that comes into my net is useful” preserves the net but drops the fish image.
- c7 / gpt-6.1-sol, by gpt-6-astra: “Keep digging away in a muddle” leaves the closing figurative expression difficult for B1 readers.
- c7 / gpt-6.1-sol, by gpt-6-astra: The unfinished “M—!” remains opaque for an independent B1 reader.
- c7 / fable-5.1, by gpt-6-astra: “Surprised” weakens Ada's being startled.
- c7 / fable-5.1, by gpt-6-astra: “Without taking such a freedom” leaves Richard's objection in an obscure expression.
- c7 / fable-5.1, by gpt-6-astra: “Given ... a name” drops the christening image.
- c7 / fable-5.1, by gpt-6-astra: “I take anything that comes my way” drops the fish-and-net image.
- c7 / fable-5.1, by gpt-6-astra: “Par्चments,” “noble and learned,” and “dig on in a mess” leave substantial vocabulary or figurative-language obstacles.
- c7 / fable-5.1, by gpt-6-astra: The unfinished “M—!” remains opaque for an independent B1 reader.
- c7 / opus-5.5, by gpt-6-astra: “Her room” narrows “her apartment” to a single room.
- c7 / opus-5.5, by gpt-6-astra: “Very grandly and seriously” adds seriousness to the old lady's stateliness.
- c7 / opus-5.5, by gpt-6-astra: “You don't need to touch it so freely” weakens Richard's firm objection into a statement about necessity.
- c7 / opus-5.5, by gpt-6-astra: “I take anything that comes my way” drops the fish-and-net image.
- c7 / opus-5.5, by gpt-6-astra: “Par्चmentses” retains a difficult word in a nonstandard form.
- c7 / opus-5.5, by gpt-6-astra: “Pretty well every day,” “sits in the Inn,” and “digging away in a muddle” remain insufficiently accessible.
- c7 / opus-5.5, by gpt-6-astra: “He don't” retains nonstandard grammar that complicates independent B1 reading.
- c7 / opus-5.5, by gpt-6-astra: The unfinished “M—!” remains opaque for an independent B1 reader.
- c7 / gpt-6-astra, by gpt-6-astra: “Surprised” weakens Ada's being startled.
- c7 / gpt-6-astra, by gpt-6-astra: “Unable to look away” strengthens the claim that Ada briefly holds the old lady's attention.
- c7 / gpt-6-astra, by gpt-6-astra: The separate sentence beginning “Usually” adds an explanatory generalization.
- c7 / gpt-6-astra, by gpt-6-astra: “Seemed to shrink back” introduces uncertainty absent from Krook's actual return to his former self.
- c7 / gpt-6-astra, by gpt-6-astra: “Given these names” drops the christening image.
- c7 / gpt-6-astra, by gpt-6-astra: “Any fish ... is welcome” retains the image but loses the explicit sense that everything acquired counts as useful.
- c7 / gpt-6-astra, by gpt-6-astra: “Great and learned man” loses the noble rank in Krook's mock-grand description of his “brother.”
- c7 / gpt-6-astra, by gpt-6-astra: “Keep digging away in a mess” leaves the closing figurative expression difficult for B1 readers.
- c7 / gpt-6-astra, by gpt-6-astra: The unfinished “M—!” remains opaque for an independent B1 reader.
- c23 / gpt-6-astra, by gpt-6-astra: Adds explanations identifying Druids as ancient priests and explaining the purpose of spurs.
- c23 / gpt-6-astra, by gpt-6-astra: “Fairly well” makes George's “Middling” response slightly more positive.
- c23 / gpt-6-astra, by gpt-6-astra: “Fully grown” loses the emphasis on George's physical development in “developed figure.”
- c23 / gpt-6-astra, by gpt-6-astra: “Devilishly” and “back-kitchen” remain difficult vocabulary for an independent B1 reader.
- c23 / opus-5.5, by gpt-6-astra: “Agree with” changes Charley's difficulty satisfying Miss Smallweed into difficulty sharing her opinions.
- c23 / opus-5.5, by gpt-6-astra: “Nobody announces him” loses the qualification “Without other announcement.”
- c23 / opus-5.5, by gpt-6-astra: Adds short hair and slow walking; neither is specified.
- c23 / opus-5.5, by gpt-6-astra: “Uniform or military equipment” narrows the source's unspecified clothes or equipment.
- c23 / opus-5.5, by gpt-6-astra: “A house so unlike him” replaces the contrast with its household.
- c23 / opus-5.5, by gpt-6-astra: “Swallow up” changes the image of absorbing the family into himself.
- c23 / opus-5.5, by gpt-6-astra: Leaves “Druidical ruins,” “spurs,” “broadsword,” “oyster-knife,” and several dialect forms insufficiently accessible for B1.
- c23 / fable-5.1, by gpt-6-astra: Identifies the unspecified ruins as bread and butter and adds speed as the reason for the reprimand.
- c23 / fable-5.1, by gpt-6-astra: “Answer Miss Smallweed's views” changes the difficulty of satisfying her expectations.
- c23 / fable-5.1, by gpt-6-astra: “Nobody announces him” loses the qualification “Without other announcement.”
- c23 / fable-5.1, by gpt-6-astra: “That last word” incorrectly locates George's emphasis on “sister” rather than “devilish.”
- c23 / fable-5.1, by gpt-6-astra: Adds short hair and narrows the unspecified clothing to a uniform.
- c23 / fable-5.1, by gpt-6-astra: “Swallow up” changes the image of absorbing the family into himself.
- c23 / fable-5.1, by gpt-6-astra: Adds an explanatory definition of circulation to Grandfather Smallweed's dialogue.
- c23 / fable-5.1, by gpt-6-astra: “Clean-shaved” is an awkward replacement for “close-shaved”; “clean-shaven” is the usual form.
- c23 / fable-5.1, by gpt-6-astra: Retains substantial B1 obstacles, including dialect spellings, “Druid-like,” “spurs,” “oyster-knife,” and “pinched ways.”
- c23 / gpt-6.1-sol, by gpt-6-astra: Adds explanations identifying Druids as ancient priests and defining spurs.
- c23 / gpt-6.1-sol, by gpt-6-astra: “Fairly well” makes George's “Middling” response slightly more positive.
- c23 / gpt-6.1-sol, by gpt-6-astra: “Grand” introduces an implication of impressiveness or dignity into George's expansive manner.
- c23 / gpt-6.1-sol, by gpt-6-astra: The final question loses the repeated “rub” that gives the original its pointed humour.
- c23 / gpt-6.1-sol, by gpt-6-astra: “Devilishly” remains difficult vocabulary for an independent B1 reader.
- c31 / gpt-6.1-sol, by gpt-6-astra: “No one would have paid anything” misreads the threatened-life idiom as a statement about payment.
- c31 / gpt-6.1-sol, by gpt-6-astra: “Damn” strengthens Guppy's mild “dash” in both places.
- c31 / gpt-6.1-sol, by gpt-6-astra: “Taken the freedom of looking” is an unnatural replacement for “taken the liberty of looking.”
- c31 / gpt-6.1-sol, by gpt-6-astra: “I dare say” remains an unexplained idiom.
- c31 / gpt-6-astra, by gpt-6-astra: “Damn” strengthens Guppy's mild “dash” in both places.
- c31 / gpt-6-astra, by gpt-6-astra: “Perhaps” softens Guppy's stated belief that she hardly remembers Esther's face.
- c31 / gpt-6-astra, by gpt-6-astra: “Knocked me over” remains unexplained and may suggest a physical fall.
- c31 / fable-5.1, by gpt-6-astra: “Did your ladyship notice” presupposes a resemblance more strongly than the original question.
- c31 / fable-5.1, by gpt-6-astra: “My 'art” leaves the dialect pronunciation of “heart” unclear for an independent B1 reader.
- c31 / fable-5.1, by gpt-6-astra: “Worth a minute's purchase” preserves an opaque historical idiom.
- c31 / fable-5.1, by gpt-6-astra: “Dash it,” “knocked me over,” “taken the liberty,” and “I dare say” remain unexplained idioms.
- c31 / fable-5.1, by gpt-6-astra: “Her steady gaze never wavers” retains unnecessarily difficult vocabulary.
- c31 / opus-5.5, by gpt-6-astra: The life-threat passage adds a separate explanatory sentence after paraphrasing the original image.
- c31 / opus-5.5, by gpt-6-astra: “Dash it,” “knocked me over,” and “I dare say” remain unexplained idioms.
- c31 / opus-5.5, by gpt-6-astra: “You was” preserves nonstandard grammar that may confuse a B1 reader.
- c31 / opus-5.5, by gpt-6-astra: The opening quotation mark before “I think your ladyship” is missing.
- c39 / gpt-6-astra, by gpt-6-astra: “Making any firm plans” narrows “doing anything very definite” to planning.
- c39 / gpt-6-astra, by gpt-6-astra: “Shocks” misrepresents the jarring discord of lawsuits.
- c39 / gpt-6-astra, by gpt-6-astra: “Whisper” adds a manner of speaking absent from “breathe” here.
- c39 / opus-5.5, by gpt-6-astra: Adds explanatory glosses after both “suitors” and “interested party.”
- c39 / opus-5.5, by gpt-6-astra: “Strange attraction” adds a judgment absent from the source.
- c39 / opus-5.5, by gpt-6-astra: “More awake than usual all night” adds an explicit duration.
- c39 / opus-5.5, by gpt-6-astra: “Whisper” adds a manner of speaking absent from “breathe” here.
- c39 / opus-5.5, by gpt-6-astra: “Spoils everybody” loses the image of contamination in “taints everybody.”
- c39 / fable-5.1, by gpt-6-astra: “Suitors, who are waiting on the court” adds an explanation without clearly conveying that they are parties to lawsuits.
- c39 / fable-5.1, by gpt-6-astra: “Spoils everybody” loses the image of contamination in “taints everybody.”
- c39 / gpt-6.1-sol, by gpt-6-astra: “Making any firm decision about what to do” narrows definite action to decision-making.
- c39 / gpt-6.1-sol, by gpt-6-astra: “The court case” narrows Richard’s general statement about suitors to this particular case.
- c39 / gpt-6.1-sol, by gpt-6-astra: The sleeping woods lose their explicit silence.
- c39 / gpt-6.1-sol, by gpt-6-astra: “My criticism had hurt that generous part of him” explains the narrator’s inference and weakens the sense of inward self-reproach.
- c39 / gpt-6.1-sol, by gpt-6-astra: “Changed me a little for the worse” removes the image of a twisted character.
- c39 / gpt-6.1-sol, by gpt-6-astra: “Harms something good in everybody” replaces the image of contamination with an explanation.
- c47 / opus-5.5, by gpt-6-astra: “In the full strength of his youth” adds physical strength; the source stresses youth despite his exhausted appearance.
- c47 / opus-5.5, by gpt-6-astra: “Going away on leave today” changes being already on leave into a planned departure on leave.
- c47 / opus-5.5, by gpt-6-astra: “I know that thing too well” adds an emphasis absent from “with my experience.”
- c47 / opus-5.5, by gpt-6-astra: “Catechism” remains unexplained vocabulary beyond the intended reading level.
- c47 / fable-5.1, by gpt-6-astra: “Full strength” adds physical strength not stated in the source.
- c47 / fable-5.1, by gpt-6-astra: “Worn and tired” loses the visibly drawn appearance conveyed by “haggard.”
- c47 / fable-5.1, by gpt-6-astra: The added gloss “giving up my place in the army” fails to convey that selling out means selling his officer’s position.
- c47 / fable-5.1, by gpt-6-astra: “Smooth things over,” “selling out,” and “catechism” remain obstacles for an independent B1 reader.
- c47 / gpt-6.1-sol, by gpt-6-astra: “Still young and handsome” drops the emphasis on being in the fullness of youth.
- c47 / gpt-6.1-sol, by gpt-6-astra: “That phrase about authority comes from the book of religious questions and answers” turns Richard’s passing allusion into an explicit explanatory aside.
- c55 / fable-5.1, by gpt-6-astra: “Shameless” loses the boldness conveyed by “audacious”.
- c55 / fable-5.1, by gpt-6-astra: “People who helped him” adds an explanatory gloss after “accomplices”.
- c55 / fable-5.1, by gpt-6-astra: “Tired” adds a condition not specified by “debilitated”.
- c55 / fable-5.1, by gpt-6-astra: Leaves difficult expressions such as “bring ... to light”, “wear off”, and “ain't” unadapted.
- c55 / opus-5.5, by gpt-6-astra: “Often” weakens “constantly”.
- c55 / opus-5.5, by gpt-6-astra: “Richer than he was” replaces the comparison with his modest appearance with a claim about his actual wealth.
- c55 / opus-5.5, by gpt-6-astra: “Protest” misleadingly suggests an objection rather than a solemn declaration.
- c55 / opus-5.5, by gpt-6-astra: “A three-cornered hat” adds an explanatory gloss after “cocked hat”.
- c55 / opus-5.5, by gpt-6-astra: “Hanged” narrows the cousin's initial wish for execution to a specific method.
- c55 / opus-5.5, by gpt-6-astra: Leaves difficult expressions such as “wear off”, “accomplices”, and “ain't” unadapted.
- c55 / gpt-6.1-sol, by gpt-6-astra: “Often” weakens “constantly”.
- c55 / gpt-6.1-sol, by gpt-6-astra: Omits “first” from the possibility that the house connection initially marked him as a target.
- c55 / gpt-6.1-sol, by gpt-6-astra: “Most trusted” describes others' confidence in him rather than his trustworthiness.
- c55 / gpt-6.1-sol, by gpt-6-astra: “A shocking lack of fear” awkwardly shifts “audacious” from outrageous boldness towards fearlessness.
- c55 / gpt-6-astra, by gpt-6-astra: “Often” weakens “constantly”.
- c55 / gpt-6-astra, by gpt-6-astra: “Watches him closely” changes Bucket's brief, observant glance into sustained attention.
- c63 / opus-5.5, by gpt-6-astra: Adds explanatory glosses for 'bribe', 'philosophy', 'prejudices' and 'lynx'.
- c63 / opus-5.5, by gpt-6-astra: Leaves 'because I want it myself' unchanged: here 'want' means lack, which a B1 reader would likely misunderstand.
- c63 / opus-5.5, by gpt-6-astra: Retains difficult expressions such as 'above suspicion', 'qualified' concepts of faith, and 'act with philosophy' rather than consistently simplifying the language.
- c63 / opus-5.5, by gpt-6-astra: Leaves the Cæsar's wife and house-that-Jack-built allusions opaque.
- c63 / gpt-6-astra, by gpt-6-astra: Adds the explanatory identification of a lynx as 'a wild cat'.
- c63 / gpt-6-astra, by gpt-6-astra: 'Not by Mr. Bucket?' no longer fits grammatically after 'No one can pay me to do something wrong.'
- c63 / gpt-6-astra, by gpt-6-astra: 'Beyond any reason for doubt' makes suspicion of wrongdoing less specific.
- c63 / gpt-6-astra, by gpt-6-astra: Leaves the Cæsar's wife and house-that-Jack-built allusions opaque.
- c63 / fable-5.1, by gpt-6-astra: Leaves 'because I want it myself' unchanged, obscuring the intended meaning 'because I lack that faith'.
- c63 / fable-5.1, by gpt-6-astra: 'A very special kind of energy' loses the idea that Bucket's energy is directed towards a particular purpose.
- c63 / fable-5.1, by gpt-6-astra: Adds explanatory restatements after 'paralyse' and 'the knowing man'.
- c63 / fable-5.1, by gpt-6-astra: 'He comfortably takes revenge' shifts the comfort towards Bucket rather than those he avenges.
- c63 / fable-5.1, by gpt-6-astra: Retains difficult language including 'even-handed', 'tamed lynx' and 'expressly', alongside opaque literary allusions.
- c63 / gpt-6.1-sol, by gpt-6-astra: 'Duties to others' narrows the source's broader 'moral obligations'.
- c63 / gpt-6.1-sol, by gpt-6-astra: Turns the narrator's gently stated moral principle about betraying trust into a more direct accusation of completed wrongdoing.
- c63 / gpt-6.1-sol, by gpt-6-astra: Breaks the cumulative house-that-Jack-built sentences into separate statements, weakening the nursery-rhyme imitation.
- c63 / gpt-6.1-sol, by gpt-6-astra: 'This matters' weakens Skimpole's claim that thinking well of Bucket is essential.
- c63 / gpt-6.1-sol, by gpt-6-astra: Leaves 'lynx', 'beyond suspicion' and both literary allusions difficult for an independent B1 reader.
