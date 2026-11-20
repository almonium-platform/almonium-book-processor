# The writers judge each other: B1 adaptation of bleak-house-en-original

Every judge saw the source and the candidates under shuffled letters, without model names. Rank 1 is best; a win is rank 1. Each judge also rated its own work, blind.

## Writing

| Writer | Passages | Output tokens | List price |
|---|---|---|---|
| opus-5.5 | 8 | 38421 | $0.96 |
| fable-5.1 | 8 | 34902 | $2.23 |
| gpt-6.1-sol | 8 | 14692 | $0.43 |
| gpt-6-astra | 8 | 14497 | $1.89 |
| gemini-4-carbon-low | 8 | 18542 | $0.34 |
| gemini-4-carbon-medium | 8 | 498815 | $5.07 |

## Level readings: passages the pipeline's judges read at B1 or under

| Writer | gpt-6.1-sol | opus-5.5 | Both |
|---|---|---|---|
| opus-5.5 | 4 of 8 | 8 of 8 | 4 of 8 |
| fable-5.1 | 1 of 8 | 6 of 8 | 1 of 8 |
| gpt-6.1-sol | 7 of 8 | 7 of 8 | 6 of 8 |
| gpt-6-astra | 6 of 8 | 8 of 8 | 6 of 8 |

## Judge: opus-5.5 (8 passages, $0.64 list)

| Writer | Mean rank | Wins | Mean score | Passages with a slip flagged |
|---|---|---|---|---|
| opus-5.5 (itself) | 2.12 | 3 (38%) | 7.1 | 8 of 8 |
| fable-5.1 | 2.12 | 2 (25%) | 7.2 | 8 of 8 |
| gpt-6-astra | 2.75 | 1 (12%) | 6.6 | 8 of 8 |
| gpt-6.1-sol | 3.00 | 2 (25%) | 6.4 | 8 of 8 |

## Judge: gpt-6-astra (8 passages, $1.79 list)

| Writer | Mean rank | Wins | Mean score | Passages with a slip flagged |
|---|---|---|---|---|
| gpt-6-astra (itself) | 1.38 | 6 (75%) | 8.0 | 7 of 8 |
| gpt-6.1-sol | 2.38 | 2 (25%) | 7.4 | 8 of 8 |
| fable-5.1 | 3.00 | 0 (0%) | 6.8 | 8 of 8 |
| opus-5.5 | 3.25 | 0 (0%) | 6.4 | 8 of 8 |

## Judge: gemini-4-carbon-medium (6 passages, $3.24 list)

| Writer | Mean rank | Wins | Mean score | Passages with a slip flagged |
|---|---|---|---|---|
| fable-5.1 | 2.67 | 1 (17%) | 6.3 | 6 of 6 |
| gemini-4-carbon-medium (itself) | 2.67 | 4 (67%) | 7.0 | 6 of 6 |
| gpt-6-astra | 3.17 | 1 (17%) | 5.8 | 6 of 6 |
| gpt-6.1-sol | 3.33 | 0 (0%) | 5.7 | 6 of 6 |
| gemini-4-carbon-low | 4.33 | 0 (0%) | 4.7 | 6 of 6 |
| opus-5.5 | 4.83 | 0 (0%) | 4.2 | 6 of 6 |

## All judges together

| Writer | Mean rank | Wins | Mean score | Rank by itself | Rank by the other judges |
|---|---|---|---|---|---|
| gpt-6-astra | 2.36 | 8 (36%) | 6.9 | 1.38 | 2.93 |
| fable-5.1 | 2.59 | 3 (14%) | 6.8 | - | - |
| gemini-4-carbon-medium | 2.67 | 4 (67%) | 7.0 | - | - |
| gpt-6.1-sol | 2.86 | 4 (18%) | 6.5 | - | - |
| opus-5.5 | 3.27 | 3 (14%) | 6.0 | 2.12 | 3.93 |
| gemini-4-carbon-low | 4.33 | 0 (0%) | 4.7 | - | - |

## Agreement on the best candidate

- opus-5.5 and gpt-6-astra: same best candidate on 1 of 8 passages
- opus-5.5 and gemini-4-carbon-medium: same best candidate on 1 of 6 passages
- gpt-6-astra and gemini-4-carbon-medium: same best candidate on 1 of 6 passages

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
- c15 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "cared for him" loses the professional medical sense of "attended him"
- c15 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "private, trusting tone" is slightly awkward for "in a tone of confidence"
- c15 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Adds "important" before "occasion"
- c15 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Leaves above-B1 items "African Station" and "goblet" unadapted
- c15 / fable-5.1, by gemini-4-carbon-medium: Adds explanatory gloss ", a kind of red wine" in narration
- c15 / fable-5.1, by gemini-4-carbon-medium: Adds unstated external fact "as his doctor" for "attended him"
- c15 / fable-5.1, by gemini-4-carbon-medium: Drops the metaphor in "a speaking likeness" ("The picture is exactly like him")
- c15 / fable-5.1, by gemini-4-carbon-medium: "adding up the facts" and "dare to correct" slightly distort the idioms
- c15 / fable-5.1, by gemini-4-carbon-medium: Leaves above-B1 or confusing items "goblet", "first-rate", and "your mistress"
- c15 / gemini-4-carbon-low, by gemini-4-carbon-medium: Drops the specific wine "claret" completely for generic "red wine"
- c15 / gemini-4-carbon-low, by gemini-4-carbon-medium: Shifts "It's a very fine head" (about the portrait) to "he has a very fine head"
- c15 / gemini-4-carbon-low, by gemini-4-carbon-medium: Flattens the narrator's ironic "we had the full benefit of them" into "we heard all about them"
- c15 / gemini-4-carbon-low, by gemini-4-carbon-medium: Invents details not in the source: "painted" (twice), "A servant", "at the table", "himself", and "as his doctor"
- c15 / opus-5.5, by gemini-4-carbon-medium: Uses wrong present tense "they are most remarkable men" for two deceased husbands
- c15 / opus-5.5, by gemini-4-carbon-medium: Drops the metaphor in "a speaking likeness" ("It looks exactly like him")
- c15 / opus-5.5, by gemini-4-carbon-medium: Adds explanatory gloss ", a kind of red wine" and explicit "I was his doctor"
- c15 / opus-5.5, by gemini-4-carbon-medium: Leaves many archaic or above-B1 expressions ("African Station", "drawing-room", "should like to have seen", "goblet", "your mistress")
- c15 / gpt-6-astra, by gemini-4-carbon-medium: Mistranslates "in a tone of confidence" (confidentially) as "confidently"
- c15 / gpt-6-astra, by gemini-4-carbon-medium: Inserts a clumsy definition into dialogue: "drinking cup, James—the one with the stem!"
- c15 / gpt-6-astra, by gemini-4-carbon-medium: Adds explanatory gloss ", a kind of red wine" and "as his doctor", plus "both" and "Someone"
- c15 / gpt-6-astra, by gemini-4-carbon-medium: Drops "pre-eminently" and weakens the narrator's irony with "enjoyed the full benefit of hearing about them"
- c15 / gpt-6-astra, by gemini-4-carbon-medium: Leaves confusing archaic "your mistress"
- c15 / gpt-6.1-sol, by gemini-4-carbon-medium: Mistranslates "in a tone of confidence" (confidentially) as "confidently"
- c15 / gpt-6.1-sol, by gemini-4-carbon-medium: Drops "The name of", putting the dead Professor Dingo in the present tense ("is famous across Europe")
- c15 / gpt-6.1-sol, by gemini-4-carbon-medium: Invents "we chose" in "we chose the same day of the year"
- c15 / gpt-6.1-sol, by gemini-4-carbon-medium: Inserts clumsy gloss "cup with a stem" in dialogue, plus ", a red wine", "Someone", and "as his doctor"
- c15 / gpt-6.1-sol, by gemini-4-carbon-medium: Drops "pre-eminently" and flattens the ironic "we had the full benefit of them" to "So we heard all about them"
- c15 / gpt-6.1-sol, by gemini-4-carbon-medium: Leaves archaic or above-B1 items ("African Station", "drawing-room", "should like to have seen", "your mistress")
- c23 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Inserts 'also' before 'breaks up the Druidical ruins', separating the gulp of tea from its direct effect ('and so disperses').
- c23 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Narrows 'withdrawing' to 'goes out', implying Charley leaves the room rather than simply stepping away to the door.
- c23 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Leaves several above-B1 words or archaic grammar unadapted ('Druidical', adverbial 'devilish like', 'spurs', 'cavalry', 'parlor', 'absorb').
- c23 / gpt-6.1-sol, by gemini-4-carbon-medium: Adds an explanation not in the source: 'ancient priests' for Druids.
- c23 / gpt-6.1-sol, by gemini-4-carbon-medium: Adds an explanation not in the source: 'the metal points riders wear on their boots' for spurs.
- c23 / gpt-6.1-sol, by gemini-4-carbon-medium: Replaces 'launching' with 'throws', losing the nautical metaphor of launching teacups into the outgoing tide.
- c23 / gpt-6.1-sol, by gemini-4-carbon-medium: Changes the colloquial adjective 'devilish' to the adverb 'devilishly', losing the grammar noted by the narrator.
- c23 / gpt-6.1-sol, by gemini-4-carbon-medium: Leaves literary 'returns' (as a speech verb) and 'for' ('because') unadapted for a B1 reader in paragraph 2.
- c23 / gemini-4-carbon-low, by gemini-4-carbon-medium: Invents 'of bread and butter' in paragraph 3 (imported from outside the passage) and mistranslates 'so disperses... that' as 'so fast that'.
- c23 / gemini-4-carbon-low, by gemini-4-carbon-medium: Spoils the dry periphrasis 'The object of her attentions withdrawing' by naming Charley, narrowing 'attentions' to 'sharp remarks', and inventing 'leaves the room'.
- c23 / gemini-4-carbon-low, by gemini-4-carbon-medium: Adds the explicit simile 'like boats' to explain 'launching'.
- c23 / gemini-4-carbon-low, by gemini-4-carbon-medium: Mistranslates 'devilish' as 'terribly', losing the hellfire echo from Mr. George's fire remark and weakening why the stress is uncomplimentary.
- c23 / gemini-4-carbon-low, by gemini-4-carbon-medium: Spoils the narrator's concluding guess early by specifying 'uniform or military equipment' before the 'horse soldier' reveal.
- c23 / gemini-4-carbon-low, by gemini-4-carbon-medium: Renders physical 'pinched ways' as moral 'mean ways', drops causal 'for' in paragraph 2, and uses unidiomatic 'You are hot in here'.
- c23 / gpt-6-astra, by gemini-4-carbon-medium: Adds an explanation not in the source: 'ancient priests' for Druids.
- c23 / gpt-6-astra, by gemini-4-carbon-medium: Adds a full explanatory sentence not in the source defining spurs ('These are the metal points riders wear on their boots to urge horses on.').
- c23 / gpt-6-astra, by gemini-4-carbon-medium: Drops the causal 'so... that' link between scattering the ruins and Miss Smallweed's order in paragraph 3.
- c23 / gpt-6-astra, by gemini-4-carbon-medium: Replaces 'launching' with 'throws' and weakens habitual 'the snappish Judy' to single-action 'Judy asks sharply'.
- c23 / gpt-6-astra, by gemini-4-carbon-medium: Changes 'seeing your granddaughter' to 'meeting your granddaughter' and 'devilish' to 'devilishly'.
- c23 / gpt-6-astra, by gemini-4-carbon-medium: Mistranslates habitual 'Do you rub your legs' as progressive 'Are you rubbing your legs', clashing with the reply 'it's partly a habit'.
- c23 / gpt-6-astra, by gemini-4-carbon-medium: Leaves literary 'returns' and 'for' in paragraph 2 and breaks the narrative into choppy, flattened sentences.
- c23 / fable-5.1, by gemini-4-carbon-medium: Invents 'of bread and butter' in paragraph 3 and mistranslates 'so disperses... that' as 'so fast that'.
- c23 / fable-5.1, by gemini-4-carbon-medium: Drops the ironic periphrasis 'The object of her attentions', replacing it with plain 'Charley', and replaces 'launching' with 'throws'.
- c23 / fable-5.1, by gemini-4-carbon-medium: Spoils the concluding guess early by translating 'dress' as 'uniform'.
- c23 / fable-5.1, by gemini-4-carbon-medium: Adds inline definitions 'a trooper, a soldier on horseback' and—unnaturally inside spoken dialogue—'the circulation, the flow of my blood'.
- c23 / fable-5.1, by gemini-4-carbon-medium: Leaves non-standard dialect and untaught idioms unadapted for B1 ('How de do?', 'ha'n't', 'in the law', 'into \'em', 'devilish like').
- c23 / fable-5.1, by gemini-4-carbon-medium: Leaves above-B1 vocabulary unadapted ('spurs', 'oyster-knife', 'stunted', 'pinched', 'parlour').
- c23 / opus-5.5, by gemini-4-carbon-medium: Mistranslates 'meeting her views' (satisfying her expectations) as 'agree with Miss Smallweed's opinions'.
- c23 / opus-5.5, by gemini-4-carbon-medium: Drops the causal 'so... that' link in paragraph 3 and leaves 'Druidical ruins' unexplained in scare quotes.
- c23 / opus-5.5, by gemini-4-carbon-medium: Flattens 'The object of her attentions' to 'The girl she has been watching' and replaces 'launching' with 'throws'.
- c23 / opus-5.5, by gemini-4-carbon-medium: Spoils the narrator's concluding guess early by specifying 'uniform or military equipment' before the 'trooper' reveal.
- c23 / opus-5.5, by gemini-4-carbon-medium: Mistranslates 'crisp dark hair' (tightly curled) as 'short and stiff', adds 'slow' to 'measured', and renders 'pinched' as 'mean'.
- c23 / opus-5.5, by gemini-4-carbon-medium: Adds the inline explanation 'a trooper, a soldier on horseback'.
- c23 / opus-5.5, by gemini-4-carbon-medium: Leaves non-standard dialect and above-B1 vocabulary unadapted ('How de do?', 'ha'n't', 'in the law', 'into \'em', 'broadsword', 'oyster-knife', 'stunted', 'spurs').
- c31 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "Thank you, your ladyship." Mr. Guppy does so. leaves "does so" awkwardly paired with "Thank you".
- c31 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "makes a proud movement... She tells him for certain" adds "proud" and implies spoken words rather than assurance by gesture alone.
- c31 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "trusting you to keep it secret" adds a slight explanatory gloss on top of "privately" for "in confidence".
- c31 / fable-5.1, by gemini-4-carbon-medium: Leaves archaic idiom "worth a minute's purchase" unadapted and opaque for a B1 reader.
- c31 / fable-5.1, by gemini-4-carbon-medium: Uses eye-dialect "'art" for "heart", which is confusing at B1, especially near "portrait".
- c31 / fable-5.1, by gemini-4-carbon-medium: Leaves many untaught idioms and C1 words in place ("dash it", "knocked me over", "taken the liberty", "in confidence", "I dare say", "scornful", "wavers").
- c31 / fable-5.1, by gemini-4-carbon-medium: Adds "long ago" in "There were times, long ago".
- c31 / gpt-6-astra, by gemini-4-carbon-medium: "damn it!" and "Damn these notes" mistranslate mild "dash" into profanity Guppy would not use to Lady Dedlock.
- c31 / gpt-6-astra, by gemini-4-carbon-medium: "Thank you, your ladyship." Mr. Guppy does so. leaves "does so" without a sensible referent after "Thank you".
- c31 / gpt-6-astra, by gemini-4-carbon-medium: "You really do look even more surprisingly like her than I thought" alters "it's really more surprising" and reverses the comparison direction.
- c31 / gpt-6-astra, by gemini-4-carbon-medium: "asks him why" changes "what... has to do with her" to "why".
- c31 / gpt-6-astra, by gemini-4-carbon-medium: Minor shifts and omissions: "a few points" for "a head or two", "Perhaps" for "I think", omits "half" in "half a moment" and "I am sure", and leaves "knocked me over".
- c31 / gemini-4-carbon-low, by gemini-4-carbon-medium: Replaces Guppy's obsequious "your ladyship" with "my Lady" throughout (14 times), losing his register and contrast with the narrator.
- c31 / gemini-4-carbon-low, by gemini-4-carbon-medium: "Mr. Guppy sits down" supplies an explanation from outside the passage for "Mr. Guppy does so".
- c31 / gemini-4-carbon-low, by gemini-4-carbon-medium: Invents "in their cage" for the love-birds.
- c31 / gemini-4-carbon-low, by gemini-4-carbon-medium: Invents "A short time ago" for the Lincolnshire trip (source only says "on a short out", a brief outing).
- c31 / gemini-4-carbon-low, by gemini-4-carbon-medium: Exaggerates "in your ladyship's hands" to "to your mercy" and flattens "worth no complaint" to "not important enough".
- c31 / gemini-4-carbon-low, by gemini-4-carbon-medium: Invents the imperative "Look at how her beautiful eyes are staring at you right now" and adds "proud", "painted", and "noble".
- c31 / gpt-6.1-sol, by gemini-4-carbon-medium: "Mr. Guppy thanks her" mistranslates "Mr. Guppy does so" (he sits down, contradicting "sits down again" at the end).
- c31 / gpt-6.1-sol, by gemini-4-carbon-medium: "damn it!" and "Damn these notes" mistranslate mild "dash" into out-of-character profanity.
- c31 / gpt-6.1-sol, by gemini-4-carbon-medium: "taken the freedom of looking" is a wrong word/unidiomatic collocation for "taken the liberty of looking".
- c31 / gpt-6.1-sol, by gemini-4-carbon-medium: "no one would have paid anything for your poor life, even for a minute" mistranslates the idiom "worth a minute's purchase" literally.
- c31 / gpt-6.1-sol, by gemini-4-carbon-medium: Compresses the two-step escalation "completely knocked me over; so much so, that I didn't at the moment even know..." and omits "half" in "half a moment" and "I am sure".
- c31 / opus-5.5, by gemini-4-carbon-medium: Copies the source's missing opening quotation mark in 'I think your ladyship," says Mr. Guppy'.
- c31 / opus-5.5, by gemini-4-carbon-medium: Leaves non-standard "you was not aware of me" unadapted in a B1 learner text.
- c31 / opus-5.5, by gemini-4-carbon-medium: Leaves most untaught idioms and hard words unadapted ("dash it", "Yes, to be sure!", "in confidence", "knocked me over", "I dare say", "see my way now, right on", "scornful", "murmurs").
- c31 / opus-5.5, by gemini-4-carbon-medium: Adds "Some time ago", "In the past", and "not even for a moment", and drops the fortified sense of "strongholds" ("castles").
- c31 / opus-5.5, by gemini-4-carbon-medium: Pads "worth a minute's purchase" into two sentences, adding "your poor life would have been worth almost nothing".
- c7 / fable-5.1, by gemini-4-carbon-medium: Anticipates 'the old lady' for 'our conductress' in paragraph 1 before paragraph 2 introduces it.
- c7 / fable-5.1, by gemini-4-carbon-medium: Omits 'stimulated' from 'stimulated by Richard's laughing encouragement'.
- c7 / fable-5.1, by gemini-4-carbon-medium: Invents 'soft and fine' and narrows 'texture' to touch in 'how soft and fine it feels!'.
- c7 / fable-5.1, by gemini-4-carbon-medium: Weakens 'strongly disapproving' to 'strongly disliked' and adds 'her' after 'admire'.
- c7 / fable-5.1, by gemini-4-carbon-medium: Uses unidiomatic wrong word 'taking such a freedom' for 'taking that liberty'.
- c7 / fable-5.1, by gemini-4-carbon-medium: Omits the 'christening' metaphor ('given me and my place a name').
- c7 / fable-5.1, by gemini-4-carbon-medium: Omits the fish-and-net image in 'all's fish that comes to my net' ('I take anything that comes my way').
- c7 / fable-5.1, by gemini-4-carbon-medium: Adds explanation 'as judge' in 'when he sits as judge in the Inn'.
- c7 / fable-5.1, by gemini-4-carbon-medium: Uses unnatural phrasal verb 'dig on' for 'grub on' and leaves C2/C1 lexis ('parchments', 'learned').
- c7 / gpt-6-astra, by gemini-4-carbon-medium: Omits 'she had taken' from 'a key she had taken from her pocket'.
- c7 / gpt-6-astra, by gemini-4-carbon-medium: Mistranslates Richard's polite formula 'had had the pleasure of seeing' as literal 'had enjoyed seeing'.
- c7 / gpt-6-astra, by gemini-4-carbon-medium: Omits 'earnest' and 'stimulated' in paragraph 1.
- c7 / gpt-6-astra, by gemini-4-carbon-medium: Omits 'condescending to him', keeping only 'far above him in importance'.
- c7 / gpt-6-astra, by gemini-4-carbon-medium: Uses wrong verb 'I promise you' for 'I assure you' and flattens 'odd' to 'strange'.
- c7 / gpt-6-astra, by gemini-4-carbon-medium: Drops the sense of admirable quality in 'what texture!' ('And how it feels!').
- c7 / gpt-6-astra, by gemini-4-carbon-medium: Invents habitual statement 'Usually, the lady's attention wandered from one thing to another.'
- c7 / gpt-6-astra, by gemini-4-carbon-medium: Weakens 'Mr. Krook shrunk' by adding 'seemed to' ('seemed to shrink back').
- c7 / gpt-6-astra, by gemini-4-carbon-medium: Omits 'wasting away' and adds 'slowly' in 'slowly falling apart and being ruined'.
- c7 / gpt-6-astra, by gemini-4-carbon-medium: Omits the 'christening' metaphor ('given these names').
- c7 / gpt-6-astra, by gemini-4-carbon-medium: Inserts explanation 'documents written on animal skin' into Krook's speech (and 'holds court' for 'sits').
- c7 / gpt-6.1-sol, by gemini-4-carbon-medium: Shifts 'had been trying' to 'was trying' and omits 'pressingly', 'earnest', and 'stimulated' in paragraph 1.
- c7 / gpt-6.1-sol, by gemini-4-carbon-medium: Mistranslates Richard's polite formula 'had had the pleasure of seeing' as literal 'had enjoyed seeing'.
- c7 / gpt-6.1-sol, by gemini-4-carbon-medium: Omits 'condescending to him', keeping only 'far above him in importance'.
- c7 / gpt-6.1-sol, by gemini-4-carbon-medium: Uses wrong verb 'I promise you' for 'I assure you' and flattens 'odd' to 'strange'.
- c7 / gpt-6.1-sol, by gemini-4-carbon-medium: Invents 'lovely' and narrows 'texture' to touch in 'How lovely it feels!'.
- c7 / gpt-6.1-sol, by gemini-4-carbon-medium: Invents habitual statement 'Usually, the old lady's attention wandered from one thing to another.'
- c7 / gpt-6.1-sol, by gemini-4-carbon-medium: Omits the 'christening' metaphor ('given me and my place these names').
- c7 / gpt-6.1-sol, by gemini-4-carbon-medium: Inserts explanation 'documents on animal skin' into Krook's speech (and 'holds court' for 'sits').
- c7 / gpt-6.1-sol, by gemini-4-carbon-medium: Omits 'fish' from the image 'all's fish that comes to my net'.
- c7 / gpt-6.1-sol, by gemini-4-carbon-medium: Invents 'that great lord' for 'noble'.
- c7 / opus-5.5, by gemini-4-carbon-medium: Prematurely adds 'the little old lady' in paragraph 1.
- c7 / opus-5.5, by gemini-4-carbon-medium: Omits 'earnest' and 'stimulated' in paragraph 1.
- c7 / opus-5.5, by gemini-4-carbon-medium: Adds inline gloss 'good sign, or' while leaving untaught C1 'omen'.
- c7 / opus-5.5, by gemini-4-carbon-medium: Invents 'fine' and narrows 'texture' to touch in 'how fine it feels!'.
- c7 / opus-5.5, by gemini-4-carbon-medium: Weakens 'strongly disapproving' to 'strongly disliked'.
- c7 / opus-5.5, by gemini-4-carbon-medium: Adds explanatory simile 'a name, as if at a christening'.
- c7 / opus-5.5, by gemini-4-carbon-medium: Omits the fish-and-net image in 'all's fish that comes to my net' ('I take anything that comes my way').
- c7 / opus-5.5, by gemini-4-carbon-medium: Leaves nonstandard dialect and untaught vocabulary ('parchmentses', 'He don't', 'sits in the Inn', 'muddle').
- c7 / gemini-4-carbon-low, by gemini-4-carbon-medium: Omits 'she had taken' and 'stimulated' in paragraph 1, and alters 'out of order' to 'broken'.
- c7 / gemini-4-carbon-low, by gemini-4-carbon-medium: Mistranslates polite formula 'had had the pleasure of seeing' as literal 'had enjoyed seeing'.
- c7 / gemini-4-carbon-low, by gemini-4-carbon-medium: Uses wrong verb 'I promise you' for 'I assure you' and narrows 'lofty station' to 'social class'.
- c7 / gemini-4-carbon-low, by gemini-4-carbon-medium: Mistranslates 'overheard' as 'heard this by chance'.
- c7 / gemini-4-carbon-low, by gemini-4-carbon-medium: Flattens 'rather carelessly' to 'without much interest'.
- c7 / gemini-4-carbon-low, by gemini-4-carbon-medium: Invents 'soft, fine' in 'what a soft, fine feel it has!'.
- c7 / gemini-4-carbon-low, by gemini-4-carbon-medium: Adds explanation 'without permission' in 'without acting so freely without permission'.
- c7 / gemini-4-carbon-low, by gemini-4-carbon-medium: Mistranslates metaphor 'shrunk into his former self' as 'went back to his quiet, shrunken manner'.
- c7 / gemini-4-carbon-low, by gemini-4-carbon-medium: Omits the 'christening' metaphor (adding 'special') and changes 'in my stock' to 'in my shop'.
- c7 / gemini-4-carbon-low, by gemini-4-carbon-medium: Inserts explanation 'animal-skin documents' for 'parchmentses'.
- c7 / gemini-4-carbon-low, by gemini-4-carbon-medium: Omits the fish-and-net image and repeats itself ('whatever comes my way is useful to me; I take everything').
- c7 / gemini-4-carbon-low, by gemini-4-carbon-medium: Adds explanations 'brother judge' and 'holds court' for 'brother... when he sits'.
- c7 / gemini-4-carbon-low, by gemini-4-carbon-medium: Omits the digging image of 'grub on' and invents 'slowly' ('work away slowly in a confused mess').
- c7 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Uses jarring modern Americanism 'Hey! Hey!' and 'Hey, Lady Jane!' for 'Hi hi!' and 'Hi, Lady Jane!'.
- c7 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Inserts dictionary-like explanation 'treated him with the polite kindness shown to someone lower in rank'.
- c7 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Alters 'rather carelessly' from manner of speaking to inner feeling ('not caring very much').
- c7 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Invents 'wonderful' in 'what a wonderful feel it has!'.
- c7 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Mistranslates 'interposed' literally as 'spoke up between them'.
- c7 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Omits the 'christening' metaphor ('given those names').
- c7 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Adds inline dictionary definition 'sheets of animal skin used for writing' for 'parchments'.
- c7 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Adds explicit explanatory simile 'like anything caught in a fisherman's net'.
- c7 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Adds explanation 'as judge' in 'when he sits as judge in the Inn'.
- c63 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "comfortably gets revenge" keeps "comfortably" literally instead of rendering its sense of "without trouble to us".
- c63 / gemini-4-carbon-medium, by gemini-4-carbon-medium: "the experienced man who knows how things work" slightly over-expands "the knowing man".
- c63 / gpt-6.1-sol, by gemini-4-carbon-medium: Replaces "for a bribe" with "for money", losing the verbal cue for "I can't be bribed."
- c63 / gpt-6.1-sol, by gemini-4-carbon-medium: Omits "remarkable" from "always remarkable for her practical good sense".
- c63 / gpt-6.1-sol, by gemini-4-carbon-medium: Replaces "produced" (brought out) with "offered" for the bank-note.
- c63 / gpt-6.1-sol, by gemini-4-carbon-medium: Breaks the cumulative "house that Jack built" syntax into separate sentences, flattening the parody.
- c63 / fable-5.1, by gemini-4-carbon-medium: Leaves "because I want it myself?" unadapted, so archaic "want" (lack) misleads a B1 reader as "desire".
- c63 / fable-5.1, by gemini-4-carbon-medium: Adds an inline explanation ("—leave him unable to act—") after "paralyse Bucket".
- c63 / fable-5.1, by gemini-4-carbon-medium: Adds an inline explanation ("the one who understands these things") after "the knowing man".
- c63 / fable-5.1, by gemini-4-carbon-medium: Leaves non-B1 syntax ("The boy being in bed, a man arrives") and vocabulary ("paralyse", "expressly").
- c63 / gpt-6-astra, by gemini-4-carbon-medium: Replaces "I can't be bribed" with active "No one can pay me to do something wrong", making "Not by Mr. Bucket?" ungrammatical.
- c63 / gpt-6-astra, by gemini-4-carbon-medium: Omits "bribe" in the narrator's turn as well, weakening the link to "How can I be bribed?"
- c63 / gpt-6-astra, by gemini-4-carbon-medium: Adds an explanation not in the source: "a wild cat, that has been trained to live with people".
- c63 / gpt-6-astra, by gemini-4-carbon-medium: Leaves archaic "directly" ("goes away from me directly" = at once), which misleads B1 readers.
- c63 / gpt-6-astra, by gemini-4-carbon-medium: Replaces "produced" with "offered" and breaks up the "house that Jack built" cumulative chain.
- c63 / opus-5.5, by gemini-4-carbon-medium: Leaves "because I want it myself?" unadapted, so archaic "want" (lack) reads as "desire".
- c63 / opus-5.5, by gemini-4-carbon-medium: Adds a dictionary gloss for "bribe" ("that is, money given to make someone do wrong").
- c63 / opus-5.5, by gemini-4-carbon-medium: Adds inline explanations for "philosophy", "Prejudices", and "lynx" ("a kind of wild cat").
- c63 / gemini-4-carbon-low, by gemini-4-carbon-medium: Mistranslates "avenges us comfortably when we are murdered" as "punishes the killer for us in a way that comforts us".
- c63 / gemini-4-carbon-low, by gemini-4-carbon-medium: Mistranslates "in its little place" as "In his own small place in the world", shifting reference to Skimpole.
- c63 / gemini-4-carbon-low, by gemini-4-carbon-medium: Drops "lynx" and invents "like a wild cat with sharp eyes, made tame".
- c63 / gemini-4-carbon-low, by gemini-4-carbon-medium: Adds explanations and inventions ("the children's rhyme about", "so pure", "tight cloth wraps", "the serious matter").
- c63 / gemini-4-carbon-low, by gemini-4-carbon-medium: Weakens "strongly object to" to "strongly dislike" and "remarkable for" to "known for".
- c55 / gpt-6-astra, by gemini-4-carbon-medium: Adds 'serving' in 'gave ... to serving me' and weakens 'constantly sat at my table' to 'often ate at my table'.
- c55 / gpt-6-astra, by gemini-4-carbon-medium: Omits 'I cannot say but that' before 'he may have been followed' and drops the 'bring ... to light' image ('uncover').
- c55 / gpt-6-astra, by gemini-4-carbon-medium: Mistranslates 'glances at him' as 'watches him closely'.
- c55 / gpt-6-astra, by gemini-4-carbon-medium: Omits 'gives Mr. Bucket to understand' and shifts 'her sensitive mind is fully made up' into Volumnia stating 'she has a sensitive mind', while dropping the 'unstrung' image.
- c55 / gpt-6-astra, by gemini-4-carbon-medium: Replaces Volumnia's legal terms ('convict', 'accomplices') with plain phrases while keeping 'or whatever they call it', losing the irony that she used the right words.
- c55 / gpt-6-astra, by gemini-4-carbon-medium: Renders 'gallantry' loosely as 'charming towards women' and shifts 'had almost said' to 'has almost called her'.
- c55 / gpt-6-astra, by gemini-4-carbon-medium: Invents 'we' in 'everything we have discovered' for 'all that has been traced' and weakens 'to his satisfaction' to 'satisfactory'.
- c55 / gpt-6-astra, by gemini-4-carbon-medium: Renders 'debilitated' as 'weak and sickly' (adding illness) and leaves the idiom 'struck down' unadapted.
- c55 / gpt-6.1-sol, by gemini-4-carbon-medium: Adds 'serving' in 'gave ... to serving me' and changes 'constantly sat at my table' to 'often ate at my table'.
- c55 / gpt-6.1-sol, by gemini-4-carbon-medium: Omits 'I cannot say but that', omits 'first' from 'even first marked', and drops the 'bring ... to light' image ('discover').
- c55 / gpt-6.1-sol, by gemini-4-carbon-medium: Mistranslates 'audacious crime' as a crime that 'showed a shocking lack of fear'.
- c55 / gpt-6.1-sol, by gemini-4-carbon-medium: Changes 'trustiest' ('most trustworthy') to 'most trusted'.
- c55 / gpt-6.1-sol, by gemini-4-carbon-medium: Omits 'gives Mr. Bucket to understand', shifts 'her sensitive mind is fully made up' to 'she has a sensitive mind', and drops the 'unstrung' image.
- c55 / gpt-6.1-sol, by gemini-4-carbon-medium: Replaces 'convict' and 'accomplices' with plain phrases while keeping 'or whatever they call it', blunting Volumnia's feigned ignorance.
- c55 / gpt-6.1-sol, by gemini-4-carbon-medium: Shifts 'had almost said' to present tense 'almost calls her'.
- c55 / gpt-6.1-sol, by gemini-4-carbon-medium: Invents 'we' in 'everything we have found out', weakens 'to his satisfaction' to 'satisfactory', and leaves 'struck down' and 'spare him' unadapted.
- c55 / fable-5.1, by gemini-4-carbon-medium: Drops Sir Leicester's shift to the dramatic present ('goes ... is struck down' becomes 'went ... was struck down') and his triple 'a gentleman who' repetition.
- c55 / fable-5.1, by gemini-4-carbon-medium: Drops the tension metaphors 'nerves are unstrung' ('ruined') and 'mind ... upon the stretch' ('working so hard').
- c55 / fable-5.1, by gemini-4-carbon-medium: Adds an inline definition ('accomplices—people who helped him—').
- c55 / fable-5.1, by gemini-4-carbon-medium: Leaves opaque archaic and above-B1 items unadapted, notably 'cocked hat', 'solemnly', 'fearsome', 'it'll wear off', 'It ain't easy', 'convict', 'bring ... to light', and 'struck down'.
- c55 / fable-5.1, by gemini-4-carbon-medium: Mistranslates 'debilitated' as 'weak, tired' and omits the cousin's clipped, drawling speech style.
- c55 / opus-5.5, by gemini-4-carbon-medium: Weakens 'constantly sat' to 'often sat'.
- c55 / opus-5.5, by gemini-4-carbon-medium: Invents 'made people think he was richer than he was' from 'possessing greater wealth ... than his own retiring demeanour would have indicated'.
- c55 / opus-5.5, by gemini-4-carbon-medium: Shifts present 'I fail' to 'I will fail' and mistranslates 'fail in the assertion of ... my fidelity' as 'fail to stay loyal'.
- c55 / opus-5.5, by gemini-4-carbon-medium: Uses the wrong word 'protest' for 'protestation' ('solemn declaration').
- c55 / opus-5.5, by gemini-4-carbon-medium: Adds an inline explanation ('a cocked hat, a three-cornered hat') and drops the 'unstrung' image ('broken').
- c55 / opus-5.5, by gemini-4-carbon-medium: Leaves above-B1 words and untaught idioms unadapted ('solemnly', 'struck down', 'spare him', 'delicate female', 'it'll wear off', 'convict', 'accomplices', 'It ain't easy', 'feeble', 'post').
- c55 / opus-5.5, by gemini-4-carbon-medium: Replaces 'executed' with 'hanged' in the cousin's opening line, losing the contrast with the next sentence.
- c55 / gemini-4-carbon-low, by gemini-4-carbon-medium: Replaces 'stain upon my name' with 'shameful mark', changes 'constantly' to 'always', and drops the 'bring ... to light' image ('uncover').
- c55 / gemini-4-carbon-low, by gemini-4-carbon-medium: Drops the dramatic present in 'goes ... and is struck down' and over-explains 'struck down' as 'attacked and killed'.
- c55 / gemini-4-carbon-low, by gemini-4-carbon-medium: Invents the explanatory phrase 'towards so grand a man' at the end of paragraph 2.
- c55 / gemini-4-carbon-low, by gemini-4-carbon-medium: Invents 'funeral' in 'Today's funeral ceremony'.
- c55 / gemini-4-carbon-low, by gemini-4-carbon-medium: Omits 'her nerves are unstrung for ever', flattening it to 'she says that she is upset forever'.
- c55 / gemini-4-carbon-low, by gemini-4-carbon-medium: Adds the explanation 'like a soldier's hat' for the cocked-hat note.
- c55 / gemini-4-carbon-low, by gemini-4-carbon-medium: Changes Bucket's patronizing 'delicate female' to 'sensitive lady'.
- c55 / gemini-4-carbon-low, by gemini-4-carbon-medium: Replaces 'convict' and 'accomplices' with plain paraphrases while keeping 'or whatever the word is', losing Volumnia's irony.
- c55 / gemini-4-carbon-low, by gemini-4-carbon-medium: Invents 'without stopping', 'for so long', 'with important people', and 'pounds', and omits the cousin's clipped speech style.
- c55 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Mistranslates 'I cannot say but that he may have been followed' into the illogical 'I cannot deny that he may have been followed'.
- c55 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Adds an explicit metalinguistic explanation ('into the three-cornered shape called a cocked hat').
- c55 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Adds inline textbook glosses for both legal terms ('find that terrible soldier guilty in court—convict him' and 'helpers in the crime—accomplices').
- c55 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Mistranslates 'in right of his importance' as 'because his importance gives him that right'.
- c55 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Leaves 'struck down' and 'spare him' unadapted while padding single expressions into doublets ('stretched and working', 'followed and found out').
- c55 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Invents 'with powerful people' for 'interest' and flattens the cousin's clipped speech into dry commentary ('He compares getting a man hanged...').
