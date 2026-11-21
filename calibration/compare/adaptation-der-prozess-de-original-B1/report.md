# The writers judge each other: B1 adaptation of der-prozess-de-original

Every judge saw the source and the candidates under shuffled letters, without model names. Rank 1 is best; a win is rank 1. Each judge also rated its own work, blind.

## Writing

| Writer | Passages | Output tokens | List price |
|---|---|---|---|
| opus-5.5 | 8 | 79185 | $1.80 |
| gpt-6.1-sol | 8 | 13705 | $0.41 |
| gpt-6-astra | 8 | 12375 | $1.29 |
| gemini-4-carbon-medium | 8 | 570341 | $5.85 |
| gemini-4-argon-medium | 8 | 13078 | $0.33 |
| gemini-4-neon-medium | 8 | 179123 | $2.81 |

## Judge: opus-5.5 (8 passages, $1.48 list)

| Writer | Mean rank | Wins | Mean score | Passages with a slip flagged |
|---|---|---|---|---|
| gemini-4-neon-medium | 2.38 | 3 (38%) | 7.6 | 7 of 8 |
| gemini-4-carbon-medium | 3.00 | 2 (25%) | 7.0 | 7 of 8 |
| gpt-6.1-sol | 3.25 | 0 (0%) | 6.9 | 7 of 8 |
| opus-5.5 (itself) | 3.50 | 2 (25%) | 6.8 | 7 of 8 |
| gpt-6-astra | 4.00 | 1 (12%) | 6.6 | 8 of 8 |
| gemini-4-argon-medium | 4.88 | 0 (0%) | 5.8 | 7 of 8 |

## Judge: gpt-6-astra (8 passages, $1.84 list)

| Writer | Mean rank | Wins | Mean score | Passages with a slip flagged |
|---|---|---|---|---|
| gpt-6-astra (itself) | 2.38 | 2 (25%) | 8.2 | 7 of 8 |
| gemini-4-carbon-medium | 2.50 | 3 (38%) | 8.1 | 6 of 8 |
| gemini-4-neon-medium | 3.25 | 2 (25%) | 8.1 | 6 of 8 |
| gpt-6.1-sol | 3.38 | 1 (12%) | 7.8 | 7 of 8 |
| opus-5.5 | 3.88 | 0 (0%) | 7.2 | 7 of 8 |
| gemini-4-argon-medium | 5.62 | 0 (0%) | 6.2 | 7 of 8 |

## Judge: gemini-4-carbon-medium (2 passages, $0.43 list)

| Writer | Mean rank | Wins | Mean score | Passages with a slip flagged |
|---|---|---|---|---|
| gemini-4-carbon-medium (itself) | 1.50 | 1 (50%) | 9.5 | 1 of 2 |
| gpt-6.1-sol | 2.00 | 1 (50%) | 8.0 | 1 of 2 |
| gemini-4-neon-medium | 3.50 | 0 (0%) | 9.0 | 1 of 2 |
| opus-5.5 | 4.50 | 0 (0%) | 7.0 | 1 of 2 |
| gemini-4-argon-medium | 4.50 | 0 (0%) | 6.5 | 1 of 2 |
| gpt-6-astra | 5.00 | 0 (0%) | 5.5 | 2 of 2 |

## All judges together

| Writer | Mean rank | Wins | Mean score | Rank by itself | Rank by the other judges |
|---|---|---|---|---|---|
| gemini-4-carbon-medium | 2.61 | 6 (33%) | 7.8 | 1.50 | 2.75 |
| gemini-4-neon-medium | 2.89 | 5 (28%) | 8.0 | - | - |
| gpt-6.1-sol | 3.17 | 2 (11%) | 7.4 | - | - |
| gpt-6-astra | 3.39 | 3 (17%) | 7.2 | 2.38 | 4.20 |
| opus-5.5 | 3.78 | 2 (11%) | 7.0 | 3.50 | 4.00 |
| gemini-4-argon-medium | 5.17 | 0 (0%) | 6.1 | - | - |

## Agreement on the best candidate

- opus-5.5 and gpt-6-astra: same best candidate on 3 of 8 passages
- opus-5.5 and gemini-4-carbon-medium: same best candidate on 1 of 2 passages
- gpt-6-astra and gemini-4-carbon-medium: same best candidate on 0 of 2 passages

## Slips flagged, for a person to check

- c0 / gpt-6-astra, by opus-5.5: Replaces the printed credit 'EINBANDENTWURF' with the added gloss 'Entwurf für den Umschlag des Buches', which changes the title-page wording of a 1925 edition.
- c0 / gpt-6-astra, by opus-5.5: 'Umschlag' (dust jacket) is not the same thing as 'Einband' (the binding).
- c1 / gemini-4-neon-medium, by opus-5.5: 'zum Steinerweichen' flattened to 'zum Verzweifeln', so the stone image is lost
- c1 / gemini-4-neon-medium, by opus-5.5: 'die hohe Schule reiten' reduced to 'Kunststücke vorführen', so the riding image is lost
- c1 / gemini-4-neon-medium, by opus-5.5: 'bei den Photographien' rendered as 'neben den Fotos'
- c1 / gemini-4-neon-medium, by opus-5.5: 'Hände in die Hüften gelegt' changed to 'gestemmt'
- c1 / gemini-4-carbon-medium, by opus-5.5: 'zum Steinerweichen' flattened to 'zum Verzweifeln', so the stone image is lost
- c1 / gemini-4-carbon-medium, by opus-5.5: 'hohe Schule reiten' reduced to 'Kunststücke vorführen'
- c1 / gemini-4-carbon-medium, by opus-5.5: 'mehr bestürzt als geärgert': adds 'verwirrt'
- c1 / gemini-4-carbon-medium, by opus-5.5: Rabensteiner's 'eleganten Trab' made 'langsamen' (invented)
- c1 / gemini-4-carbon-medium, by opus-5.5: 'selbständigen Männern': adds 'erwachsenen'
- c1 / gemini-4-carbon-medium, by opus-5.5: 'friedlich und im Guten': a doubled phrase where the source has one
- c1 / gpt-6.1-sol, by opus-5.5: 'mächtigen Leib' narrowed to 'Bauch'
- c1 / gpt-6.1-sol, by opus-5.5: 'die Menschlichkeit verbot' rendered awkwardly as 'aus Mitgefühl nicht erlaubt'
- c1 / gpt-6.1-sol, by opus-5.5: 'Aufseher hatte ihm die drei Beamten verdeckt' becomes 'Wegen des Aufsehers hatte er ... nicht erkannt', so the physical blocking is lost
- c1 / gpt-6.1-sol, by opus-5.5: 'Rüge' made 'auch noch zurechtgewiesen' (adds 'auch noch')
- c1 / gpt-6.1-sol, by opus-5.5: Very short, choppy sentences flatten the rhythm in places
- c1 / opus-5.5, by opus-5.5: Adds a gloss: 'Manschetten, also die Enden seiner Hemdärmel'
- c1 / opus-5.5, by opus-5.5: Adds a gloss: 'chronischen, also dauernden, Muskelzerrung'
- c1 / opus-5.5, by opus-5.5: Adds an explanatory sentence after 'Geistesgegenwart' ('Er hatte also nicht wach und klar ...')
- c1 / opus-5.5, by opus-5.5: 'wie in der hohen Schule der Reitkunst' leaves the idiom in, with an explanation added
- c1 / gemini-4-argon-medium, by opus-5.5: 'Automobil' changed to 'Taxi'
- c1 / gemini-4-argon-medium, by opus-5.5: 'chronische Muskelzerrung' changed to 'Krampf in seinen Gesichtsmuskeln'
- c1 / gemini-4-argon-medium, by opus-5.5: Adds 'beim Gehen' to Rabensteiner's hand-swinging
- c1 / gemini-4-argon-medium, by opus-5.5: Adds 'auf der anderen Straßenseite'
- c1 / gemini-4-argon-medium, by opus-5.5: 'zum Steinerweichen' flattened to 'zum Weinen'
- c1 / gemini-4-argon-medium, by opus-5.5: 'reichte ihm die Hand' rendered as 'gab ihm die Hand', which suggests a handshake that did not happen
- c1 / gpt-6-astra, by opus-5.5: Uses the old spelling throughout ('daß', 'Gewiß', 'mußte'), which is unsuitable for a learner
- c1 / gpt-6-astra, by opus-5.5: 'hohe Schule reiten' reduced to 'schwierige Kunststücke', so the horse image is lost
- c1 / gpt-6-astra, by opus-5.5: 'die Menschlichkeit verbot' becomes 'die Rücksicht auf einen Mitmenschen'
- c1 / gpt-6-astra, by opus-5.5: 'Geistesgegenwart' rendered as 'schnell erfaßte, was um ihn herum geschah', which turns it into an explanation
- c1 / gpt-6-astra, by opus-5.5: 'mächtigen Leib' narrowed to 'Bauch'
- c2 / gemini-4-carbon-medium, by opus-5.5: 'versucht, etwas zu erreichen' misreads 'etwas auszurichten', which here means delivering a message.
- c2 / gemini-4-carbon-medium, by opus-5.5: 'karikieren' is spelled out with an added purpose clause ('um sich über ihn lustig zu machen').
- c2 / gemini-4-neon-medium, by opus-5.5: The cushion line adds an explanation: 'damit ihr Kopf vom Druck gegen die Decke nicht schmerzhaft und wund wurde'.
- c2 / gemini-4-neon-medium, by opus-5.5: 'Murren' becomes the weaker 'Murmeln', which loses the sense of grumbling.
- c2 / gemini-4-argon-medium, by opus-5.5: 'schräg' (diagonal) mistranslates 'der Quere nach' (crosswise).
- c2 / gemini-4-argon-medium, by opus-5.5: 'gegnerische Gruppen' invents hostility between the two sides.
- c2 / gemini-4-argon-medium, by opus-5.5: 'feierliche Jacken' loses the 'holiday coats' idea.
- c2 / gemini-4-argon-medium, by opus-5.5: 'Diese Leute sind leicht für sich zu gewinnen' is ungrammatical: 'für sich' points back to the people, not to K.
- c2 / gemini-4-argon-medium, by opus-5.5: 'Erst dann machte einer...' garbles the 'only when' logic.
- c2 / gemini-4-argon-medium, by opus-5.5: 'befragen' weakens 'verhören'.
- c2 / gpt-6-astra, by opus-5.5: An explanatory gloss is added: 'Galerie, dem erhöhten Bereich über dem Saal'.
- c2 / gpt-6-astra, by opus-5.5: The 'allgemeines Murren' image is flattened to 'äußerten ... unzufrieden ihren Ärger'.
- c2 / gpt-6-astra, by opus-5.5: 'es zeigte sich' (K. discovering the path) is dropped.
- c2 / opus-5.5, by opus-5.5: An explanatory gloss is added: 'Podium, also eine kleine erhöhte Fläche'.
- c2 / opus-5.5, by opus-5.5: An explanatory gloss is added: 'Sie brummten alle unzufrieden'.
- c2 / opus-5.5, by opus-5.5: An explanation is added: 'Man sagte ja, er sei zu spät gekommen, aber er widersprach nicht'.
- c2 / opus-5.5, by opus-5.5: An explanatory gloss is added: 'also den Tisch des Richters, der die Untersuchung führte'.
- c2 / opus-5.5, by opus-5.5: 'etwas auszurichten' is left in, although it is not B1 vocabulary in this sense.
- c2 / opus-5.5, by opus-5.5: 'sprachen und bewegten sich nur zu Leuten ... hin' is clumsy.
- c2 / gpt-6.1-sol, by opus-5.5: An explanatory gloss is added: 'Galerie, dem oberen Teil des Saales'.
- c2 / gpt-6.1-sol, by opus-5.5: The causal link ('da der Mann nichts mehr sagte') is lost.
- c2 / gpt-6.1-sol, by opus-5.5: 'es zeigte sich' is dropped.
- c3 / gemini-4-neon-medium, by opus-5.5: 'Ich schwöre es' drops K.'s oath on his salvation ('so wahr ich selig werden will').
- c3 / gemini-4-neon-medium, by opus-5.5: 'drehte sich zu dem Mann um' makes 'wandte sich an' (addressed him) into a physical turn.
- c3 / gemini-4-neon-medium, by opus-5.5: 'fasste sie sogar mit der Hand an' says he touched the scabbard, where the source only has him reach toward it.
- c3 / gpt-6-astra, by opus-5.5: 'bei meinem Seelenheil' is too hard for a B1 reader.
- c3 / gpt-6-astra, by opus-5.5: 'die Gelenkkrankheit Gicht' adds an explanation that is not in the source.
- c3 / gpt-6-astra, by opus-5.5: 'Er hatte gelernt, vielen anderen überlegen zu sein' shifts 'Überlegenheit, die er sich erworben hatte' (superiority he had earned).
- c3 / gpt-6-astra, by opus-5.5: The Beweisanträge line gets an explanatory sentence added ('Darin habe ich verlangt...').
- c3 / gemini-4-argon-medium, by opus-5.5: 'Wie gedemütigt und klein diese Menschen sich fühlen müssen' adds 'und klein' and turns their state into a feeling.
- c3 / gemini-4-argon-medium, by opus-5.5: 'wegen der Gelenkkrankheit Gicht' adds a gloss.
- c3 / gemini-4-argon-medium, by opus-5.5: The Beweisanträge are glossed with an explanatory clause ('damit bestimmte Beweise geprüft werden').
- c3 / opus-5.5, by opus-5.5: 'Die Scheide, also die Hülle des Säbels' adds a gloss.
- c3 / opus-5.5, by opus-5.5: 'Beweisanträge ..., also Anträge, dass das Gericht Beweise prüfen soll' adds a gloss.
- c3 / opus-5.5, by opus-5.5: 'Gicht, einer Krankheit der Gelenke' adds a gloss.
- c3 / opus-5.5, by opus-5.5: 'lange Holzbänke befestigt, also zwei Reihen' is clumsy.
- c3 / gemini-4-carbon-medium, by opus-5.5: 'In seiner ganzen Art machte sich der Mann klein und ordnete sich unter' expands 'demütiges Wesen' into an explanation.
- c3 / gemini-4-carbon-medium, by opus-5.5: 'Das ist genauso wahr, wie ich einmal in den Himmel kommen will' is an awkward, garbled oath.
- c3 / gemini-4-carbon-medium, by opus-5.5: 'woanders' is repeated, which is redundant.
- c3 / gemini-4-carbon-medium, by opus-5.5: 'Beweisanträge ... gemacht ... erledigt' is left unexplained and too hard for B1.
- c3 / gemini-4-carbon-medium, by opus-5.5: 'dass jeder Schritt so genau begrenzt war' is stilted.
- c3 / gpt-6.1-sol, by opus-5.5: 'Wie sehr man diese Menschen erniedrigt haben muss' mistranslates K.'s remark: it was about their state, and D makes someone else the cause.
- c3 / gpt-6.1-sol, by opus-5.5: 'ihre Knie blieben leicht gebeugt' softens 'die Knie geknickt'.
- c3 / gpt-6.1-sol, by opus-5.5: 'grüßte mit der Hand an der Stirn' adds an explanation for 'salutierte'.
- c3 / gpt-6.1-sol, by opus-5.5: 'Gicht, einer Krankheit der Gelenke' adds a gloss.
- c3 / gpt-6.1-sol, by opus-5.5: 'Er hatte ihn auch nur ganz leicht berührt' weakens 'angegriffen' (took hold of him).
- c8 / gemini-4-carbon-medium, by opus-5.5: 'das offizielle Schreiben' adds 'offizielle', which is not in the source
- c8 / gemini-4-carbon-medium, by opus-5.5: 'Berge von Arbeit' and 'abgeschüttelt' are idioms a B1 reader may not know
- c8 / gemini-4-carbon-medium, by opus-5.5: 'zum Anwalt gezogen' keeps the unusual verb 'ziehen'
- c8 / gpt-6.1-sol, by opus-5.5: 'unerhört' becomes 'noch nie vorgekommen', which narrows the meaning
- c8 / gpt-6.1-sol, by opus-5.5: 'schwanken' becomes 'sich verändern', which loses the sense of going back and forth
- c8 / gpt-6.1-sol, by opus-5.5: 'schwerfällig' becomes 'der so langsam arbeitete', which is a slight paraphrase
- c8 / gemini-4-argon-medium, by opus-5.5: 'Advokat' is kept throughout and is not B1 vocabulary
- c8 / gemini-4-argon-medium, by opus-5.5: 'schriftliche Gesuch' is above B1 level
- c8 / gemini-4-argon-medium, by opus-5.5: 'nicht einmal im Gedanken' makes 'nicht mit Gedanken spielen' stronger than the source
- c8 / gemini-4-argon-medium, by opus-5.5: 'Das zeigte sich auch an diesem Wintervormittag' changes the framing slightly
- c8 / gpt-6-astra, by opus-5.5: 'überwältigend schwierig' becomes 'so schwierig, dass es ihn überforderte', which shifts the meaning
- c8 / gpt-6-astra, by opus-5.5: In 'Sie sollten nicht weiter durch das Gitter schauen', it is unclear whether 'Sie' means the officials or the messengers
- c8 / gpt-6-astra, by opus-5.5: Splitting the shame sentence leaves 'daran' without a clear reference
- c8 / gpt-6-astra, by opus-5.5: 'Am besten noch an diesem Abend.' is a sentence fragment
- c8 / gemini-4-neon-medium, by opus-5.5: 'Diese Fähigkeiten hatten ihm das ermöglicht.' has no clear reference and breaks the logic
- c8 / gemini-4-neon-medium, by opus-5.5: 'dürfte'/'müsste' keep the subjunctive, which a B1 reader may read as 'might'
- c8 / gemini-4-neon-medium, by opus-5.5: 'Eingabe' is kept without help, and 'entsprechend dem Prozess zu schwanken' is not B1 level
- c8 / gemini-4-neon-medium, by opus-5.5: 'Nach seinen Erzählungen' keeps the unclear 'seinen' (the lawyer's or K.'s)
- c8 / opus-5.5, by opus-5.5: Adds an explanation: 'zum Advokaten, also zum Anwalt'
- c8 / opus-5.5, by opus-5.5: Adds an explanation: 'unerhört, also fast nie geschehen'
- c8 / opus-5.5, by opus-5.5: Adds an explanation: 'die Eingabe, also das schriftliche Gesuch an das Gericht'
- c8 / opus-5.5, by opus-5.5: The sentence about his conviction appears twice ('wurde ihm das ganz klar' / 'konnte sich gegen diese Überzeugung nicht wehren')
- c8 / opus-5.5, by opus-5.5: 'An solchen Tagen' turns this one morning into a general habit
- c9 / opus-5.5, by opus-5.5: 'Er hatte einen zweifelhaften Menschen … einladen wollen' turns the source's hypothetical ('Wenn es möglich war, daß…') into a statement of fact
- c9 / gpt-6.1-sol, by opus-5.5: 'knöpfte den Mantel … zu': in the source he buttons the collar, not the coat
- c9 / gpt-6.1-sol, by opus-5.5: 'bis dicht unter dem Hals': should be the accusative 'den Hals'
- c9 / gemini-4-neon-medium, by opus-5.5: Wrong tense in past narration: 'dass er die Empfehlung schätzt', 'überlegt', 'treffen kann'
- c9 / gemini-4-neon-medium, by opus-5.5: 'verhältnismäßig' (relatively) is dropped from the opening comparison
- c9 / gemini-4-carbon-medium, by opus-5.5: 'mit gesammelten Kräften auftreten' is a literary phrase kept as it is, and is hard for a B1 reader
- c9 / gemini-4-carbon-medium, by opus-5.5: 'aus der Hand zu geben' is an idiom left unexplained, added onto 'schicken'
- c9 / gemini-4-carbon-medium, by opus-5.5: 'außer Haus' is added; it is not in the source
- c9 / gpt-6-astra, by opus-5.5: 'Briefe von sich zu geben' is the wrong expression ('von sich geben' means to say or utter something)
- c9 / gpt-6-astra, by opus-5.5: Adds an explanation: 'in dem deutlich stand, worum es ging'
- c9 / gpt-6-astra, by opus-5.5: 'bis dicht unter dem Hals' should be 'den Hals', and it is the coat being buttoned rather than the collar
- c9 / gemini-4-argon-medium, by opus-5.5: Invents a window: 'Durch das Fenster sah man' (in the source they look through the open door)
- c9 / gemini-4-argon-medium, by opus-5.5: 'durch einen offenen Brief': 'offener Brief' means a public open letter, not a clear one ('deutlich')
- c9 / gemini-4-argon-medium, by opus-5.5: 'wenn Sie beim nächsten Mal wiederkämen' gets 'nächstens' (soon) wrong
- c9 / gemini-4-argon-medium, by opus-5.5: 'Sie hatten nun völlig umsonst gewartet' drops the ironic 'sollten'
- c18 / gpt-6-astra, by opus-5.5: Adds an explanation that is not in the source: 'dass ich nicht wissen würde, welche Entscheidung richtig war'.
- c18 / gpt-6-astra, by opus-5.5: 'an seine Brust klopfen' weakens the image of beating one's breast ('an deren Brust schlagen').
- c18 / gpt-6-astra, by opus-5.5: 'fand sich ... ab' is weaker than 'ausgesöhnt' (reconciled).
- c18 / gpt-6-astra, by opus-5.5: 'Rückgrat meines gesamten Lebens im Denken und im Geist' is a clumsy rendering of 'geistigen Existenz'.
- c18 / gpt-6.1-sol, by opus-5.5: Adds 'nach meinem Tod' to Brod's own will.
- c18 / gpt-6.1-sol, by opus-5.5: Adds an explanation: 'Was ich auch tue, ich muss dabei gegen mein Gewissen handeln'.
- c18 / gpt-6.1-sol, by opus-5.5: Adds details: 'kürzere Erzählungen' and 'zu einem Band'.
- c18 / gpt-6.1-sol, by opus-5.5: Weakens 'erzwungen' (forced) into a general 'erbittert kämpfen'.
- c18 / opus-5.5, by opus-5.5: Adds a gloss on Herostratos: 'also die Zerstörung von etwas Wertvollem'.
- c18 / opus-5.5, by opus-5.5: Turns the counterfactual into a possibility ('Vielleicht hat er ... ernst gemeint'), which blunts Brod's argument.
- c18 / gemini-4-neon-medium, by opus-5.5: Drops the Herostratos allusion ('herostratische Tat').
- c18 / gemini-4-neon-medium, by opus-5.5: Adds 'schreckliche' to the deed.
- c18 / gemini-4-neon-medium, by opus-5.5: 'hervorholen' loses the sense of stirring up ('aufrühren').
- c18 / gemini-4-carbon-medium, by opus-5.5: Drops the Herostratos allusion and adds 'schreckliche'.
- c18 / gemini-4-carbon-medium, by opus-5.5: Renders 'peinlicher' (embarrassing) as 'schmerzlichen und quälenden', which changes the meaning.
- c18 / gemini-4-carbon-medium, by opus-5.5: Pads 'Rückgrat' with an added 'der feste Halt'.
- c18 / gemini-4-carbon-medium, by opus-5.5: 'etwas so Schweres' shifts the sense of 'so etwas zumuten'.
- c18 / gemini-4-argon-medium, by opus-5.5: Adds an explanation of Herostratos: 'der ein großes Werk vernichtete'.
- c18 / gemini-4-argon-medium, by opus-5.5: Drops the breast-beating image and the higher court ('Berufungsinstanz') from the letter, and invents 'Trost suchen'.
- c18 / gemini-4-argon-medium, by opus-5.5: Renders 'peinlich' as 'schmerzhafte' and adds 'dunkle Erinnerungen'.
- c18 / gemini-4-argon-medium, by opus-5.5: Softens 'fanatische Verehrung' to 'leidenschaftlich'.
- c18 / gemini-4-argon-medium, by opus-5.5: Adds 'zu einem Buch verbunden' and 'Ein Hungerkünstler'.
- c17 / gemini-4-neon-medium, by opus-5.5: 'griff er sofort und ohne anzuhalten' loses the hastiness of 'haschte er förmlich'
- c17 / gemini-4-carbon-medium, by opus-5.5: Adds the gloss 'dem erhöhten Platz zum Predigen' after Kanzel
- c17 / gemini-4-carbon-medium, by opus-5.5: 'machte einen krummen Rücken, hockte sich hin und machte sich klein' is clumsy and wordy for 'sich zusammenkauern'
- c17 / gemini-4-carbon-medium, by opus-5.5: 'Er rief: „Josef K.!“' after 'Ausreden:' gives two colons in a row
- c17 / gemini-4-carbon-medium, by opus-5.5: Leaves 'überrennt' and 'Frauenjägern' unglossed, which is hard for B1
- c17 / opus-5.5, by opus-5.5: Adds the gloss 'also alle Zuhörer' to Gemeinde
- c17 / opus-5.5, by opus-5.5: Adds the gloss 'dem Geländer der Kanzel' to Brüstung
- c17 / opus-5.5, by opus-5.5: Adds the gloss 'also der Priester des Gefängnisses' to Gefängniskaplan
- c17 / opus-5.5, by opus-5.5: Missing question mark after 'nicht die wahre Hilfe ist'
- c17 / gpt-6-astra, by opus-5.5: Misreads the stained-glass image: the windows themselves 'bildeten eine dunkle Wand', but in the source the windows cannot break up the dark wall
- c17 / gpt-6-astra, by opus-5.5: 'hob eine Hand vom Geländer': in the source the hand is raised on the railing
- c17 / gpt-6-astra, by opus-5.5: 'Er rennt über den Gerichtstisch und den Angeklagten hinweg' softens 'überrennt' (runs them down)
- c17 / gpt-6-astra, by opus-5.5: 'Jetzt kannten ihn sogar Leute': it is unclear whether 'ihn' means K. or his name
- c17 / gpt-6.1-sol, by opus-5.5: 'Wie glaubst du, dass es enden wird?' is ungrammatical German
- c17 / gpt-6.1-sol, by opus-5.5: Misreads the stained-glass image: the windows 'wirkten wie eine dunkle Wand'
- c17 / gpt-6.1-sol, by opus-5.5: Expands 'Vorurteil' with the invented 'ohne mich zu kennen'
- c17 / gpt-6.1-sol, by opus-5.5: 'Ich bin der Geistliche für die Gefangenen im Gefängnis' is redundant
- c17 / gpt-6.1-sol, by opus-5.5: 'eine mächtige Stimme, die geübt im Sprechen war' is clumsy
- c17 / gpt-6.1-sol, by opus-5.5: 'hob eine Hand vom Geländer, ohne eine klare Geste zu machen' changes the gesture
- c17 / gemini-4-argon-medium, by opus-5.5: Invents 'Jetzt mussten sie sich nichts mehr vormachen'
- c17 / gemini-4-argon-medium, by opus-5.5: 'Wie schön war es früher gewesen' adds 'früher' and changes the meaning
- c17 / gemini-4-argon-medium, by opus-5.5: Adds the gloss 'dem erhöhten Platz für den Prediger'
- c17 / gemini-4-argon-medium, by opus-5.5: Expands the lower-court sentence with the explanation 'an ein höheres Gericht weitergehen, sondern…'
- c17 / gemini-4-argon-medium, by opus-5.5: Expands 'Vorurteil' with the invented 'ohne die Wahrheit zu kennen'
- c17 / gemini-4-argon-medium, by opus-5.5: 'Sie bringen auch die Leute dazu, die nichts…' is an incomplete sentence: 'dazu' points to nothing
- c17 / gemini-4-argon-medium, by opus-5.5: 'alle Kirchenbesucher ersetzen' shifts the meaning of 'die Gemeinde darstellen'
- c17 / gemini-4-argon-medium, by opus-5.5: 'mit langen, schnellen Schritten' drops the image of 'fliegend'
- c17 / gemini-4-argon-medium, by opus-5.5: 'Album mit Bildern' adds a detail not in the source
- c1 / gemini-4-argon-medium, by gpt-6-astra: „Gab ihm die Hand“ behauptet zunächst einen Handschlag, der tatsächlich verweigert wird.
- c1 / gemini-4-argon-medium, by gpt-6-astra: Eine chronische Muskelzerrung wird zu einem dauerhaften Krampf.
- c1 / gemini-4-argon-medium, by gpt-6-astra: „Zum Weinen“ lässt das Bild des erweichenden Steins weg.
- c1 / gemini-4-argon-medium, by gpt-6-astra: Das Bild des anspruchsvollen Reitens wird zum Vorführen von Kunststücken als dressiertes Pferd.
- c1 / gemini-4-argon-medium, by gpt-6-astra: Die Gruppe gegenüber „stand“, obwohl die Alten erst aufstehen wollen.
- c1 / gemini-4-argon-medium, by gpt-6-astra: „Ziemlich aufgeregt“ verstärkt die zurückhaltende Beschreibung seiner Aufregung.
- c1 / gemini-4-argon-medium, by gpt-6-astra: „Besprechen müssen“ macht aus einer möglichen privaten Angelegenheit eine notwendige Besprechung.
- c1 / gemini-4-argon-medium, by gpt-6-astra: Die nur erschlossene Verlegenheit der Angestellten wird als Tatsache dargestellt.
- c1 / gemini-4-argon-medium, by gpt-6-astra: „Ihm war alles gleichgültig“ verallgemeinert Rabensteiners situative Charakterisierung.
- c1 / gemini-4-argon-medium, by gpt-6-astra: Der elegante Trab verliert sein konkretes Bewegungsbild.
- c1 / gemini-4-argon-medium, by gpt-6-astra: Frau Grubachs geringes Schuldbewusstsein wird zu scheinbar völlig fehlendem schlechten Gewissen.
- c1 / gemini-4-argon-medium, by gpt-6-astra: „Ohne Grund tief“ verändert „unnötig tief“: Kritisiert wird die Tiefe des Einschneidens.
- c1 / gemini-4-argon-medium, by gpt-6-astra: Das gegenseitige Verdecken von Aufseher und Angestellten wird ausdrücklich auf versperrte Sicht reduziert.
- c1 / gpt-6.1-sol, by gpt-6-astra: Das Reitbild wird verändert: K. führt Kunststücke wie ein dressiertes Pferd vor, statt die hohe Schule zu reiten.
- c1 / gpt-6.1-sol, by gpt-6-astra: „Diese Leute drängen sich überall hinein“ fügt dem Vorwurf der Aufdringlichkeit eine allgemeine Verhaltensbehauptung hinzu.
- c1 / gpt-6.1-sol, by gpt-6-astra: „Dem alles gleichgültig war“ verallgemeinert Rabensteiners Charakterisierung.
- c1 / gpt-6.1-sol, by gpt-6-astra: „Den Blick auf den Aufseher verstellt“ verengt das Verdecken durch die Angestellten auf eine räumliche Sichtbehinderung.
- c1 / opus-5.5, by gpt-6-astra: Die Manschetten erhalten eine zusätzliche Worterklärung.
- c1 / opus-5.5, by gpt-6-astra: „Chronischen, also dauernden“ fügt eine ausdrückliche Worterklärung hinzu.
- c1 / opus-5.5, by gpt-6-astra: Der Satz nach „Geistesgegenwart“ erklärt den bereits wiedergegebenen Gedanken zusätzlich.
- c1 / opus-5.5, by gpt-6-astra: „Ziemlich aufgeregt“ verstärkt die zurückhaltende Beschreibung seiner Aufregung.
- c1 / opus-5.5, by gpt-6-astra: „Besprechen müssen“ macht aus einer möglichen privaten Angelegenheit eine notwendige Besprechung.
- c1 / opus-5.5, by gpt-6-astra: Die Leute gegenüber „standen“, obwohl die Alten erst aufstehen wollen.
- c1 / opus-5.5, by gpt-6-astra: „Mit den Händen schwenkte“ ist eine unpassende Wiedergabe von „die Hände schwingenden“.
- c1 / opus-5.5, by gpt-6-astra: Die nur erschlossene Verlegenheit der Angestellten wird als erkennbare Tatsache dargestellt.
- c1 / opus-5.5, by gpt-6-astra: „Er lief nicht richtig“ fügt dem eleganten Trab eine wertende Erklärung hinzu.
- c1 / gemini-4-neon-medium, by gpt-6-astra: „Zum Verzweifeln“ ersetzt das Bild des erweichenden Steins und verschiebt den Gefühlsakzent.
- c1 / gemini-4-neon-medium, by gpt-6-astra: Die Kunststücke lassen das Reitbild weg.
- c1 / gemini-4-neon-medium, by gpt-6-astra: Die Leute gegenüber „standen“, obwohl die Alten erst aufstehen wollen.
- c1 / gemini-4-neon-medium, by gpt-6-astra: Die nur erschlossene Verlegenheit der Angestellten wird als erkennbar dargestellt.
- c1 / gemini-4-neon-medium, by gpt-6-astra: Der Mann tritt aus dem Haustor heraus; im Original erscheint er darin.
- c1 / gemini-4-neon-medium, by gpt-6-astra: Das gegenseitige Verdecken von Aufseher und Angestellten wird ausdrücklich auf versperrte Sicht reduziert.
- c1 / gemini-4-neon-medium, by gpt-6-astra: Der „hintere Rand“ ersetzt das konkrete Hinterdeck des Autos.
- c1 / gpt-6-astra, by gpt-6-astra: Die schwierigen Kunststücke lassen das Reitbild weg.
- c1 / gpt-6-astra, by gpt-6-astra: Die dekorative Funktion der Schmuckdecke wird durch ein bloßes Schönheitsurteil ersetzt.
- c1 / gpt-6-astra, by gpt-6-astra: Die leichten, eleganten Schritte lassen das konkrete Bild des Trabs weg.
- c1 / gpt-6-astra, by gpt-6-astra: „Hinteres Verdeck“ verwechselt das Hinterdeck mit dem Fahrzeugdach.
- c1 / gpt-6-astra, by gpt-6-astra: „Bot noch sein Grinsen an“ legt eine aktive Geste nahe, obwohl Kaminers Lächeln unwillkürlich ist.
- c1 / gemini-4-carbon-medium, by gpt-6-astra: „Zum Verzweifeln“ ersetzt das Bild des erweichenden Steins und verschiebt den Gefühlsakzent.
- c1 / gemini-4-carbon-medium, by gpt-6-astra: Die Kunststücke lassen das Reitbild weg.
- c1 / gemini-4-carbon-medium, by gpt-6-astra: Die nur erschlossene Verlegenheit der Angestellten wird als erkennbar dargestellt.
- c1 / gemini-4-carbon-medium, by gpt-6-astra: Der ausdrücklich „langsame“ Lauf ergänzt eine nicht ausdrücklich genannte Geschwindigkeit und verliert das Trab-Bild.
- c1 / gemini-4-carbon-medium, by gpt-6-astra: „Hinterer Teil“ verallgemeinert das konkrete Hinterdeck des Autos.
- c2 / opus-5.5, by gpt-6-astra: Adds an explanatory definition of the podium.
- c2 / opus-5.5, by gpt-6-astra: Adds an explanatory definition of the investigating judge.
- c2 / opus-5.5, by gpt-6-astra: Turns the ambiguous renewed murmuring into a definite misunderstanding by the audience.
- c2 / opus-5.5, by gpt-6-astra: Says the murmuring becomes quieter rather than eventually dies away.
- c2 / gpt-6.1-sol, by gpt-6-astra: Omits that the man behind the seated official is standing.
- c2 / gpt-6.1-sol, by gpt-6-astra: Adds an explanatory gloss defining the gallery.
- c2 / gemini-4-argon-medium, by gpt-6-astra: Changes the table’s position from crosswise to diagonal.
- c2 / gemini-4-argon-medium, by gpt-6-astra: Explicitly makes the two groups opponents, which the source does not establish.
- c2 / gemini-4-argon-medium, by gpt-6-astra: Changes clothes worn for holidays into clothes described as solemn.
- c2 / gemini-4-argon-medium, by gpt-6-astra: Restricts K.’s hoped-for temporary support to a short time.
- c2 / gemini-4-argon-medium, by gpt-6-astra: Turns the ambiguous renewed murmuring into a definite misunderstanding.
- c2 / gemini-4-argon-medium, by gpt-6-astra: The reflexive wording in 'Diese Leute sind leicht für sich zu gewinnen' muddles whose support K. hopes to secure.
- c2 / gpt-6-astra, by gpt-6-astra: Adds an explanatory gloss defining the gallery.
- c2 / gpt-6-astra, by gpt-6-astra: Makes the initial murmuring an explicit expression of anger, strengthening the source’s more restrained description.
- c2 / gemini-4-carbon-medium, by gpt-6-astra: Changes the boy’s attempt to deliver a message into the vague attempt to achieve something.
- c2 / gemini-4-carbon-medium, by gpt-6-astra: Turns the ambiguous renewed murmuring into a definite misunderstanding.
- c2 / gemini-4-neon-medium, by gpt-6-astra: Says the murmuring becomes quieter rather than eventually dies away.
- c3 / gpt-6-astra, by gpt-6-astra: “Er hatte gelernt … überlegen zu sein” turns acquired superiority into a learned ability.
- c3 / gpt-6-astra, by gpt-6-astra: “Gelenkkrankheit” adds a medical explanation absent from the source.
- c3 / gpt-6-astra, by gpt-6-astra: “Bei meinem Seelenheil” leaves a difficult religious expression unexplained for B1 readers.
- c3 / gpt-6.1-sol, by gpt-6-astra: “Leicht gebeugt” weakens the image of buckled knees.
- c3 / gpt-6.1-sol, by gpt-6-astra: “Eine Stellung erreicht” makes the man's acquired superiority specifically a matter of position.
- c3 / gpt-6.1-sol, by gpt-6-astra: “Einer Krankheit der Gelenke” adds a medical explanation absent from the source.
- c3 / gemini-4-neon-medium, by gpt-6-astra: “Anträge auf Beweise” inaccurately suggests requests for evidence rather than motions to take evidence.
- c3 / gemini-4-neon-medium, by gpt-6-astra: “Ich schwöre es” drops the oath's reference to salvation.
- c3 / gemini-4-neon-medium, by gpt-6-astra: “Eine überlegene Stellung erarbeitet” narrows acquired superiority to an achieved position.
- c3 / gemini-4-neon-medium, by gpt-6-astra: “Salutierte” and “Gicht” remain obstacles for an independent B1 reader.
- c3 / opus-5.5, by gpt-6-astra: The action of turning toward the nearest man is omitted.
- c3 / opus-5.5, by gpt-6-astra: “Es zeigten auch viele kleine Einzelheiten” is grammatically incomplete.
- c3 / opus-5.5, by gpt-6-astra: “Also Anträge, dass das Gericht Beweise prüfen soll” inserts an explanatory gloss into the man's dialogue.
- c3 / opus-5.5, by gpt-6-astra: “Die Scheide, also die Hülle des Säbels” adds an explanatory gloss.
- c3 / opus-5.5, by gpt-6-astra: “Einer Krankheit der Gelenke” adds a medical explanation.
- c3 / opus-5.5, by gpt-6-astra: “Salutierte” remains unnecessarily difficult for B1.
- c3 / gemini-4-carbon-medium, by gpt-6-astra: “Jeder Schritt so genau begrenzt” introduces precision absent from the tentative image of steps measured out by gout.
- c3 / gemini-4-carbon-medium, by gpt-6-astra: “Beweisanträge” remains an unexplained specialist term.
- c3 / gemini-4-carbon-medium, by gpt-6-astra: “Das ist genauso wahr, wie ich einmal in den Himmel kommen will” is an awkward rendering of the religious oath.
- c3 / gemini-4-argon-medium, by gpt-6-astra: “Gedemütigt und klein … sich fühlen” changes humiliation into an explicitly described subjective feeling.
- c3 / gemini-4-argon-medium, by gpt-6-astra: “Ich schwöre bei Gott” replaces the oath about personal salvation with a different religious oath.
- c3 / gemini-4-argon-medium, by gpt-6-astra: “Sich über ihn lustig machte” turns a possible joke into ridicule.
- c3 / gemini-4-argon-medium, by gpt-6-astra: “Anträge auf Beweise” inaccurately suggests requests for evidence.
- c3 / gemini-4-argon-medium, by gpt-6-astra: “Gelenkkrankheit” adds a medical explanation absent from the source.
- c3 / gemini-4-argon-medium, by gpt-6-astra: “Sich wieder gefangen” and “auf die Nerven” introduce idioms that hinder independent B1 reading.
- c8 / opus-5.5, by gpt-6-astra: „Gebracht“ schwächt das widerstrebende Mitgezogenwerden in „zum Advokaten gezogen“.
- c8 / opus-5.5, by gpt-6-astra: Die eingeschobenen Definitionen von „Advokat“ und „Eingabe“ sind zusätzliche Erklärungen.
- c8 / opus-5.5, by gpt-6-astra: „Unerhört, also fast nie geschehen“ fügt eine Häufigkeitsbehauptung hinzu und verliert den empörenden Charakter.
- c8 / gemini-4-argon-medium, by gpt-6-astra: „Gebracht“ schwächt das widerstrebende Mitgezogenwerden in „zum Advokaten gezogen“.
- c8 / gemini-4-argon-medium, by gpt-6-astra: „Sich … verändern“ verliert das Auf und Ab in Bürstners Verhältnis zu K.
- c8 / gpt-6-astra, by gpt-6-astra: „Sich mit dem Prozess verändern“ verliert das Auf und Ab in Bürstners Verhältnis zu K.
- c8 / gpt-6-astra, by gpt-6-astra: „Der Anwalt sollte ihn dann nicht mehr vertreten“ erklärt zusätzlich den unmittelbar zuvor genannten Auftragsentzug.
- c8 / gpt-6-astra, by gpt-6-astra: „Der so langsam arbeitete“ reduziert die Schwerfälligkeit des Anwalts auf sein Arbeitstempo.
- c8 / gpt-6.1-sol, by gpt-6-astra: „Gebracht“ schwächt das widerstrebende Mitgezogenwerden in „zum Advokaten gezogen“.
- c8 / gpt-6.1-sol, by gpt-6-astra: „Sich mit dem Prozess verändern“ verliert das Auf und Ab in Bürstners Verhältnis zu K.
- c8 / gpt-6.1-sol, by gpt-6-astra: „Noch nie vorgekommen“ macht aus „unerhört“ eine eindeutige historische Behauptung und verliert den empörenden Charakter.
- c8 / gpt-6.1-sol, by gpt-6-astra: „Der so langsam arbeitete“ reduziert die Schwerfälligkeit des Anwalts auf sein Arbeitstempo.
- c9 / opus-5.5, by gpt-6-astra: „Er hatte … einladen wollen“ macht aus der zunächst hypothetischen Selbstprüfung eine feste Aussage über seine Absicht.
- c9 / opus-5.5, by gpt-6-astra: „Herandrängen“ verstärkt das bloße Herankommen um ein körperliches Drängen.
- c9 / gemini-4-neon-medium, by gpt-6-astra: „Hatten … völlig umsonst gewartet“ ersetzt „gewartet haben sollten“ durch eine feststehende Bilanz.
- c9 / gpt-6-astra, by gpt-6-astra: „Er war für die Empfehlung dankbar“ ersetzt die Wertschätzung, die K. lediglich zeigen möchte, durch tatsächlich empfundene Dankbarkeit.
- c9 / gpt-6-astra, by gpt-6-astra: „Eine ausführliche Antwort in einem Brief“ legt die im Original nur als schriftlich bezeichnete Antwort auf einen Brief fest.
- c9 / gemini-4-carbon-medium, by gpt-6-astra: „Wenn es nach K. ging“ schreibt K. eine Haltung zum vergeblichen Warten zu, die das Original nicht ausdrücklich behauptet.
- c9 / gpt-6.1-sol, by gpt-6-astra: „Er war für die Empfehlung dankbar“ ersetzt die Wertschätzung, die K. lediglich zeigen möchte, durch tatsächlich empfundene Dankbarkeit.
- c9 / gpt-6.1-sol, by gpt-6-astra: „Dann würde ich … in einem Brief antworten“ schwächt die feste Zusage ab und legt die schriftliche Antwort zusätzlich auf einen Brief fest.
- c9 / gemini-4-argon-medium, by gpt-6-astra: „Vielleicht … auch“ verwischt die ausdrücklich alternativ angebotenen Möglichkeiten eines Besuchs oder eines Briefs.
- c9 / gemini-4-argon-medium, by gpt-6-astra: „Offenen Brief“ ist keine passende Wiedergabe von „deutlichen Brief“ und kann einen öffentlichen Brief bezeichnen.
- c9 / gemini-4-argon-medium, by gpt-6-astra: „Er war bereit gewesen“ macht aus der hypothetischen Selbstprüfung eine feststehende Bereitschaft.
- c9 / gemini-4-argon-medium, by gpt-6-astra: „War … nur durch eine Tür … getrennt“ stellt die räumliche Situation des gedachten Treffens als tatsächlich gegeben dar.
- c9 / gemini-4-argon-medium, by gpt-6-astra: „Dann war es sogar sehr wahrscheinlich“ ersetzt K.s beunruhigte Frage durch eine Feststellung.
- c9 / gemini-4-argon-medium, by gpt-6-astra: „Zeigte auf drei Herren“ erfindet eine konkrete Zeigegeste.
- c9 / gemini-4-argon-medium, by gpt-6-astra: „Genaue schriftliche Antwort“ ersetzt Ausführlichkeit durch Genauigkeit.
- c9 / gemini-4-argon-medium, by gpt-6-astra: „Beim nächsten Mal“ gibt „nächstens“ nicht wieder und macht die Einladung zur Wiederkehr tautologisch.
- c9 / gemini-4-argon-medium, by gpt-6-astra: „Sie hatten nun völlig umsonst gewartet“ beseitigt die Perspektive des vermeintlich vergeblichen Wartens.
- c9 / gemini-4-argon-medium, by gpt-6-astra: „Durch das Fenster“ fügt ein Fenster hinzu und lässt den ausdrücklich beschriebenen Blick durch die offene Zimmertür weg.
- c17 / gemini-4-neon-medium, by gpt-6-astra: „Rennt den Gerichtstisch und den Angeklagten um“ changes running over them into knocking them over.
- c17 / gemini-4-neon-medium, by gpt-6-astra: „Gefängniskaplan“, „Frauenjäger“ and the figurative „Siehst du denn nicht zwei Schritte weit?“ remain difficult for an independent B1 reader.
- c17 / gpt-6-astra, by gpt-6-astra: „Wohl nicht mehr gehen“ weakens K.’s certainty that leaving during the sermon will be impossible.
- c17 / gpt-6-astra, by gpt-6-astra: The windows themselves become a dark wall; the source describes their glass paintings failing to interrupt the darkness of the wall.
- c17 / gpt-6-astra, by gpt-6-astra: „Ständig hinter Frauen her“ adds an explicit claim of constant pursuit.
- c17 / gpt-6-astra, by gpt-6-astra: „Hinter Frauen her“ and „Siehst du denn nicht zwei Schritte weit?“ leave figurative expressions unresolved for B1 readers.
- c17 / opus-5.5, by gpt-6-astra: „Wohl nicht mehr tun“ weakens the certainty that K. cannot leave during the sermon.
- c17 / opus-5.5, by gpt-6-astra: „Also alle Zuhörer“ adds a gloss and reduces the religious meaning of „Gemeinde“ to an audience.
- c17 / opus-5.5, by gpt-6-astra: „Dem Geländer der Kanzel“ and „also der Priester des Gefängnisses“ add explanatory glosses.
- c17 / opus-5.5, by gpt-6-astra: „Leg es weg“ loses the specific instruction to put the album out of his hand.
- c17 / opus-5.5, by gpt-6-astra: „Rennt den Gerichtstisch und den Angeklagten um“ changes running over them into knocking them over.
- c17 / opus-5.5, by gpt-6-astra: „Hinter Frauen her“ and „Siehst du denn nicht zwei Schritte weit?“ retain difficult figurative language.
- c17 / gemini-4-carbon-medium, by gpt-6-astra: „Dem erhöhten Platz zum Predigen“ adds an explanation of the pulpit.
- c17 / gemini-4-carbon-medium, by gpt-6-astra: „Machte einen krummen Rücken“ turns the servant’s bent posture into an additional deliberate movement.
- c17 / gemini-4-carbon-medium, by gpt-6-astra: „Gefängniskaplan“, „Frauenjäger“, „überrennt“ and the final figurative question remain demanding for B1 readers.
- c17 / gemini-4-argon-medium, by gpt-6-astra: „Alle Kirchenbesucher ersetzen“ changes constituting the congregation into replacing other visitors.
- c17 / gemini-4-argon-medium, by gpt-6-astra: „Saß … da“ loses the servant’s movement of crouching down.
- c17 / gemini-4-argon-medium, by gpt-6-astra: „Runde Decken“ inaccurately replaces the vaulted architecture.
- c17 / gemini-4-argon-medium, by gpt-6-astra: The echo’s ordered progression becomes repetition accompanying K.’s walking.
- c17 / gemini-4-argon-medium, by gpt-6-astra: „Dem erhöhten Platz für den Prediger“ adds an explanatory gloss.
- c17 / gemini-4-argon-medium, by gpt-6-astra: „Jetzt mussten sie sich nichts mehr vormachen“ invents mutual pretence.
- c17 / gemini-4-argon-medium, by gpt-6-astra: „Schnellen Schritten“ drops the image of flying steps.
- c17 / gemini-4-argon-medium, by gpt-6-astra: „Schriftlichen Antrag“ narrows the unspecified court submission to an application.
- c17 / gemini-4-argon-medium, by gpt-6-astra: „Unzufrieden“ substitutes dissatisfaction for the priest’s disapproval.
- c17 / gemini-4-argon-medium, by gpt-6-astra: „Rennt … um“ changes running over the table and defendant into knocking them over.
- c17 / gemini-4-argon-medium, by gpt-6-astra: „Kleine Dach“ adds an unsupported size.
- c17 / gemini-4-argon-medium, by gpt-6-astra: „Großen Altar“ loses the identification of the main altar.
- c17 / gemini-4-argon-medium, by gpt-6-astra: „Wütend auf mich“ intensifies K.’s question about whether the priest is displeased with him.
- c17 / gemini-4-argon-medium, by gpt-6-astra: The final figurative question remains difficult for B1 readers.
- c17 / gpt-6.1-sol, by gpt-6-astra: „Wohl nicht mehr gehen“ weakens the certainty that K. cannot leave during the sermon.
- c17 / gpt-6.1-sol, by gpt-6-astra: „Ohne mich zu kennen“ adds a specific basis for prejudice that K. does not state.
- c17 / gpt-6.1-sol, by gpt-6-astra: The priest’s denial of prejudice becomes a broader denial of having a bad opinion of K.
- c17 / gpt-6.1-sol, by gpt-6-astra: „Dass dir das nicht wirklich hilft“ replaces the distinction between true and other help with a claim about practical effectiveness.
- c17 / gpt-6.1-sol, by gpt-6-astra: „Ständig hinter Frauen her“ adds an explicit claim of constant pursuit.
- c17 / gpt-6.1-sol, by gpt-6-astra: „Rennt den Gerichtstisch und den Angeklagten um“ changes running over them into knocking them over.
- c17 / gpt-6.1-sol, by gpt-6-astra: The windows become the dark wall instead of failing to illuminate or interrupt it.
- c17 / gpt-6.1-sol, by gpt-6-astra: „Hinter Frauen her“ and the final figurative question remain difficult for B1 readers.
- c18 / gpt-6.1-sol, by gpt-6-astra: Adds the claim that either possible decision necessarily violates the narrator’s conscience.
- c18 / gpt-6.1-sol, by gpt-6-astra: Replaces the image of the friend as the narrator’s backbone with a generic support.
- c18 / gpt-6.1-sol, by gpt-6-astra: Changes forcing every publication into fighting to publish every individual text.
- c18 / gpt-6-astra, by gpt-6-astra: Adds that Kafka foresaw the narrator not knowing which decision was right.
- c18 / gpt-6-astra, by gpt-6-astra: Makes nonpublication into a categorical decision to publish nothing.
- c18 / gpt-6-astra, by gpt-6-astra: Changes striking the imagined authority’s breast to knocking on it.
- c18 / gemini-4-argon-medium, by gpt-6-astra: Adds an explanation of Herostratos and his destruction of a great work.
- c18 / gemini-4-argon-medium, by gpt-6-astra: Narrows the unspecified things to be reviewed to papers.
- c18 / gemini-4-argon-medium, by gpt-6-astra: Replaces infinite blessing with infinite happiness.
- c18 / gemini-4-argon-medium, by gpt-6-astra: Drops the backbone image.
- c18 / gemini-4-argon-medium, by gpt-6-astra: Replaces nihilism with a wholly hopeless outlook.
- c18 / gemini-4-argon-medium, by gpt-6-astra: Changes personally embarrassing periods into personally painful periods.
- c18 / gemini-4-argon-medium, by gpt-6-astra: Replaces the shadows image with dark memories.
- c18 / gemini-4-argon-medium, by gpt-6-astra: Drops the image of striking the higher authority’s breast and adds seeking consolation.
- c18 / gemini-4-argon-medium, by gpt-6-astra: Changes the letter’s personal hope for help in distress into an impersonal account.
- c18 / gemini-4-neon-medium, by gpt-6-astra: Drops the Herostratos allusion.
- c18 / gemini-4-neon-medium, by gpt-6-astra: Broadens the specific picture postcard to any postcard.
- c18 / opus-5.5, by gpt-6-astra: Adds an explanatory gloss defining the Herostratos comparison as destruction of something valuable.
- c18 / opus-5.5, by gpt-6-astra: Recasts the counterfactual about Kafka’s absolute seriousness as an explicit possibility: 'Vielleicht hat er … ernst gemeint.'
- c18 / gemini-4-carbon-medium, by gpt-6-astra: Changes categorically expressed instructions into instructions expressed 'without exception.'
- c18 / gemini-4-carbon-medium, by gpt-6-astra: Drops the Herostratos allusion.
- c18 / gemini-4-carbon-medium, by gpt-6-astra: Changes personally embarrassing periods into painful and tormenting periods.
- c0 / gpt-6-astra, by gemini-4-carbon-medium: Replaces the bibliographic credit 'EINBANDENTWURF' with the clunky explanatory paraphrase 'Entwurf für den Umschlag des Buches:', shifting 'Einband' (binding) to 'Umschlag' (jacket/cover) and breaking the all-caps imprint style.
- c2 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Leaves above-B1 noun 'Murren' in place, padding its first occurrence with redundant 'unzufriedenes'.
- c2 / gemini-4-carbon-medium, by gemini-4-carbon-medium: Adds 'vielleicht' to K.'s concessive 'Mag ich zu spät gekommen sein', slightly softening his defiant tone.
- c2 / gemini-4-neon-medium, by gemini-4-carbon-medium: Mistranslates 'mißverständlich' as ambiguity in the crowd's murmur, breaking the causal logic of 'Denn'.
- c2 / gemini-4-neon-medium, by gemini-4-carbon-medium: Retains archaic dative 'winkte den Leuten mit der Hand ab', ungrammatical in modern Standard German.
- c2 / gemini-4-neon-medium, by gemini-4-carbon-medium: Omits 'fast' in 'Er sah nur die Rücken' after splitting 'kaum ein ... sondern nur', contradicting 'kaum ein Gesicht'.
- c2 / gemini-4-neon-medium, by gemini-4-carbon-medium: Softens 'durcheinanderwimmelnden Gedränge', audible 'schnaufender', and 'Murren' ('Murmeln').
- c2 / gpt-6.1-sol, by gemini-4-carbon-medium: Inserts an added explanation for 'Galerie' ('dem oberen Teil des Saales').
- c2 / gpt-6.1-sol, by gemini-4-carbon-medium: Mistranslates 'mißverständlich' as ambiguity in the murmur, breaking the causal logic of 'Denn'.
- c2 / gpt-6.1-sol, by gemini-4-carbon-medium: Uses literary synthetic Konjunktiv II ('als zählte', 'als machte') identical to Präteritum and hard to parse at B1.
- c2 / gpt-6.1-sol, by gemini-4-carbon-medium: Omits 'angeblichen' ('gegen den Vorwurf') and drops the mockery element of 'karrikiere'.
- c2 / gpt-6.1-sol, by gemini-4-carbon-medium: Weakens concessive 'Mag ich ... sein' to 'Vielleicht ... aber', formal 'erscheinen' to 'hier sein', and 'schnell' to 'kurz'.
- c2 / gpt-6-astra, by gemini-4-carbon-medium: Inserts an added explanation for 'Galerie' ('dem erhöhten Bereich über dem Saal').
- c2 / gpt-6-astra, by gemini-4-carbon-medium: Erases the auditory image of 'Murren' ('äußerten ... unzufrieden ihren Ärger') and omits 'allgemeines'.
- c2 / gpt-6-astra, by gemini-4-carbon-medium: Mistranslates 'mißverständlich' as ambiguity ('nicht klar, wie sie zu verstehen waren') and omits causal 'denn'.
- c2 / gpt-6-astra, by gemini-4-carbon-medium: Uses above-B1 synthetic Konjunktiv I and II forms ('als zählte', 'als mache', 'er sei zu spät gekommen').
- c2 / gpt-6-astra, by gemini-4-carbon-medium: Weakens concessive 'Mag ich ... sein' to 'Vielleicht ... aber', drops 'es zeigte sich', and inverts 'soweit man ... unterscheiden konnte' with 'Allerdings'.
- c2 / opus-5.5, by gemini-4-carbon-medium: Inserts three explicit vocabulary explanations ('Podium', 'murren', 'Untersuchungsrichters') that violate fidelity and flatten the prose.
- c2 / opus-5.5, by gemini-4-carbon-medium: Leaves above-B1 or archaic forms unadapted ('etwas auszurichten', 'winkte den Leuten ... ab', 'schnaufte', 'murren', Konjunktiv I 'sei').
- c2 / opus-5.5, by gemini-4-carbon-medium: Narrows 'Bezirksversammlung' by adding 'Stadt-' ('Stadtbezirk').
- c2 / gemini-4-argon-medium, by gemini-4-carbon-medium: Mistranslates 'der Quere nach' (crosswise) as 'schräg' (diagonally) and 'Feiertagsröcken' (holiday coats) as 'feierliche Jacken' (solemn jackets).
- c2 / gemini-4-argon-medium, by gemini-4-carbon-medium: Replaces 'zwei Parteien' with 'zwei gegnerische Gruppen' (inventing 'gegnerische', dropping 'Parteien') and indoor 'Galerie' with 'Balkon'.
- c2 / gemini-4-argon-medium, by gemini-4-carbon-medium: Contains a reflexive grammar error in 'Diese Leute sind leicht für sich zu gewinnen' ('für sich' refers to 'Diese Leute' instead of K.).
- c2 / gemini-4-argon-medium, by gemini-4-carbon-medium: Leaves archaic 'Geld aufzählte' (modern meaning: 'enumerate') and weakens judicial 'verhören' to 'befragen'.
- c2 / gemini-4-argon-medium, by gemini-4-carbon-medium: Paraphrases 'Untersuchungsrichters' ('des Richters, der den Fall untersuchte'), invents 'wild' and 'ruhig zu sein', omits 'fast' before 'nur die Rücken', and weakens 'Mag ich ... sein'.
