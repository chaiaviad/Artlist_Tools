"""
muse.py — the Companion's "surprise me" idea generator.

Middle-click the companion and it jiggles, "thinks", then drops a random
creative-writing prompt of the shape:

    Hero1 [and Hero2] <action> [with/against], in <location>,
    in the mood and style of <genre>.

Every element is assembled from large modular word banks (adjective + role +
origin, etc.), so the pool of possibilities is astronomically large.

Coherence ("logic check") is built in — instant, no AI / no network:
  * actions are matched to the relationship (solo / together / against), so the
    sentence is always grammatical;
  * each LOCATION has a SETTING (sea/space/urban/gothic/rural/wild) and each
    GENRE lists the settings that fit it, so the location is logical for the
    genre;
  * each ACTION carries theme DOMAINS (crime/horror/comedy/scifi/...) and each
    GENRE lists its domains, so the chosen action is semantically consistent
    with the genre.
  Characters stay free — a quirky character in any genre reads as flavour.
"""

import os
import random

# --------------------------------------------------------------------------- #
#  Characters
# --------------------------------------------------------------------------- #
CHAR_ADJ = [
    "weary", "exiled", "radiant", "one-eyed", "immortal", "disgraced",
    "cybernetic", "feral", "aristocratic", "time-lost", "lovesick", "vengeful",
    "half-blind", "golden-toothed", "soft-spoken", "storm-touched", "bankrupt",
    "undercover", "retired", "doomed", "luminous", "rust-covered", "barefoot",
    "masked", "insomniac", "grief-stricken", "razor-tongued", "sleepwalking",
    "fireproof", "amnesiac", "silver-haired", "tattooed", "shipwrecked",
    "two-faced", "honey-voiced", "battle-scarred", "moonstruck", "penniless",
    "clockwork", "saintly", "wolfish", "stone-cold", "hopeless", "ravenous",
    "velvet-gloved", "hollow-eyed", "iron-willed", "perfumed", "shivering",
    "gilded", "feverish", "lopsided", "thunderstruck", "world-weary",
    "lightfingered", "porcelain", "scarred", "dust-caked", "neon-lit",
    "salt-stained", "smoke-cured", "glass-jawed", "moth-eaten", "ageless",
    "hot-headed", "ice-blooded", "double-jointed", "snake-charming",
    "well-mannered", "ill-tempered", "long-lost", "newly-widowed",
    "down-on-their-luck", "silver-tongued", "broad-shouldered", "twitchy",
    "soot-streaked", "candle-thin", "war-painted", "moon-faced", "bramble-haired",
    "gaunt", "sun-blistered", "frost-bitten", "tin-eared", "leather-bound",
    "absent-minded", "razor-thin", "bear-like", "owl-eyed", "ink-stained",
    "tar-black", "honey-eyed", "crooked", "unblinking", "champagne-soaked",
    "switchblade-quick", "moth-winged",
]
CHAR_ROLE = [
    "lighthouse keeper", "jazz trumpeter", "bounty hunter", "marine biologist",
    "séance medium", "getaway driver", "court jester", "war photographer",
    "beekeeper", "android nun", "cartographer", "smuggler", "taxidermist",
    "opera singer", "street magician", "ferryman", "librarian", "astronaut",
    "fortune teller", "prize boxer", "clockmaker", "gravedigger", "chef",
    "spy", "swamp witch", "disgraced knight", "test pilot", "private detective",
    "perfumer", "lion tamer", "ice fisher", "radio host", "forger",
    "exorcist", "sommelier", "lock-picker", "snake charmer", "undertaker",
    "cosmonaut", "pearl diver", "puppeteer", "arms dealer", "monk",
    "tightrope walker", "coroner", "stunt double", "tomb raider",
    "tattoo artist", "ventriloquist", "rodeo clown", "glassblower",
    "bell-ringer", "falconer", "cat burglar", "weather forecaster",
    "mortician", "carnival barker", "deep-sea welder", "organ grinder",
    "sword swallower", "telegraph operator", "fire-eater", "beekeeper queen",
    "midwife", "shepherd", "cult leader", "auctioneer", "watchmaker",
    "diplomat", "saboteur", "cartoonist", "whaler", "alchemist",
    "switchboard operator", "balloonist", "embalmer", "card sharp",
    "lighthouse mechanic", "fortune hunter", "ghost writer", "bodyguard",
    "tax collector", "circus strongman", "nightclub singer", "poison taster",
    "submarine cook", "dream interpreter", "bank teller", "snake-oil seller",
    "war correspondent", "demolitions expert", "palace guard", "scarecrow maker",
    "ice cream vendor", "professional mourner", "lighthouse painter",
    "retired assassin", "traveling dentist", "map forger", "bog-body curator",
    "moonshiner", "kite maker", "bone-setter", "tunnel digger",
]
# character TYPES / archetypes — who they are, not what they do (mixed into the
# role pool so heroes aren't all professions)
CHAR_TYPE = [
    "runaway", "stranger", "widow", "orphan", "twin", "dreamer", "liar",
    "drifter", "hermit", "outcast", "prophet", "fugitive", "gambler",
    "romantic", "cynic", "idealist", "wanderer", "loner", "survivor", "heir",
    "heiress", "impostor", "recluse", "daydreamer", "troublemaker", "scapegoat",
    "prodigy", "has-been", "misfit", "firebrand", "sweetheart", "scoundrel",
    "rogue", "vagabond", "nomad", "pilgrim", "newcomer", "old-timer",
    "daredevil", "contrarian", "skeptic", "lone wolf", "free spirit",
    "wild card", "black sheep", "sore loser", "born liar", "lost soul",
    "true believer", "false prophet", "sleepwalker", "ringleader", "turncoat",
    "stowaway", "castaway", "deserter", "mercenary", "zealot", "dropout",
    "double agent", "kept secret", "runaway bride", "reluctant hero",
    "perfect stranger", "creature of habit", "hopeless romantic", "know-it-all",
    "bad influence", "lost cause", "only witness", "wallflower", "shut-in",
]
# heroes draw from jobs + types together
CHAR_NOUN = CHAR_ROLE + CHAR_TYPE

# Genre fit for characters: roles/types with a STRONG genre pull are tagged with
# theme domains so they only show up in matching genres (no astronaut in a
# western, no exorcist in a screwball comedy). Anything not listed is universal
# ("any") and can appear in any genre — keeps ordinary folk (chef, stranger,
# drifter) flexible and the variety high.
CHAR_NOUN_DOMAINS = {
    # jobs
    "bounty hunter": {"crime", "violence", "adventure"},
    "getaway driver": {"crime"}, "séance medium": {"supernatural", "horror"},
    "war photographer": {"war", "drama"}, "smuggler": {"crime", "adventure"},
    "spy": {"crime", "war", "mystery"},
    "swamp witch": {"supernatural", "horror", "fantasy"},
    "disgraced knight": {"fantasy", "adventure", "violence"},
    "test pilot": {"scifi"}, "private detective": {"crime", "mystery"},
    "exorcist": {"supernatural", "horror"}, "lock-picker": {"crime"},
    "undertaker": {"horror", "drama"}, "cosmonaut": {"scifi"},
    "astronaut": {"scifi"}, "arms dealer": {"crime", "war"},
    "tomb raider": {"adventure", "supernatural"},
    "coroner": {"mystery", "crime", "horror"}, "forger": {"crime", "mystery"},
    "cat burglar": {"crime"}, "mortician": {"horror", "drama"},
    "saboteur": {"war", "crime"}, "whaler": {"adventure", "survival"},
    "alchemist": {"fantasy", "supernatural", "scifi"},
    "bodyguard": {"crime", "violence"},
    "demolitions expert": {"war", "crime", "adventure"},
    "palace guard": {"fantasy", "adventure"}, "war correspondent": {"war", "drama"},
    "retired assassin": {"crime", "violence"}, "moonshiner": {"crime", "drama"},
    "gravedigger": {"horror", "drama"}, "prize boxer": {"drama", "violence"},
    "snake-oil seller": {"crime", "comedy"}, "card sharp": {"crime", "comedy"},
    "fortune teller": {"supernatural", "mystery"}, "fortune hunter": {"adventure"},
    "nightclub singer": {"romance", "drama", "crime"},
    "deep-sea welder": {"adventure", "survival"},
    "cult leader": {"horror", "supernatural", "drama"},
    "monk": {"drama", "supernatural", "fantasy"},
    "falconer": {"fantasy", "adventure"}, "lion tamer": {"adventure", "comedy"},
    "snake charmer": {"adventure", "supernatural"}, "pearl diver": {"adventure"},
    "poison taster": {"crime", "drama"}, "diplomat": {"war", "drama", "crime"},
    "circus strongman": {"adventure", "comedy"}, "rodeo clown": {"comedy"},
    "carnival barker": {"comedy"}, "ventriloquist": {"horror", "comedy"},
    "puppeteer": {"horror", "drama"}, "sword swallower": {"adventure", "comedy"},
    "fire-eater": {"adventure", "comedy"}, "stunt double": {"drama", "adventure"},
    # world/era-flavoured roles (locked so they don't leak into the wrong genre)
    "android nun": {"scifi", "drama"}, "court jester": {"comedy", "fantasy", "drama"},
    "telegraph operator": {"war", "drama", "mystery"},
    "switchboard operator": {"crime", "war", "drama"},
    "submarine cook": {"adventure", "survival", "war"}, "balloonist": {"adventure"},
    "scarecrow maker": {"horror", "drama"}, "bog-body curator": {"horror", "mystery"},
    "organ grinder": {"drama", "comedy"},
    # types
    "fugitive": {"crime", "survival"}, "gambler": {"crime", "drama"},
    "mercenary": {"war", "violence", "crime"}, "deserter": {"war"},
    "zealot": {"war", "horror", "drama"},
    "double agent": {"crime", "war", "mystery"}, "turncoat": {"war", "crime"},
    "stowaway": {"adventure"}, "castaway": {"survival", "adventure"},
    "prophet": {"supernatural", "drama", "fantasy"},
    "false prophet": {"supernatural", "horror", "drama"},
    "true believer": {"drama", "war", "supernatural"},
    "ringleader": {"crime", "comedy"}, "daredevil": {"adventure"},
    "sleepwalker": {"horror", "supernatural"},
    "lost soul": {"horror", "supernatural", "drama"}, "survivor": {"survival"},
    "hopeless romantic": {"romance", "drama"}, "sweetheart": {"romance"},
    "widow": {"drama", "romance"}, "reluctant hero": {"adventure", "drama"},
    "scoundrel": {"crime", "adventure", "comedy"},
    "rogue": {"crime", "adventure", "fantasy"},
}
CHAR_ORIGIN = [
    "from a drowned city", "from the year 3000", "with nothing left to lose",
    "who can't remember yesterday", "raised by wolves", "on the run",
    "in witness protection", "fresh out of prison", "with a borrowed name",
    "who sold their shadow", "haunted by a single song", "with one week to live",
    "wanted in three countries", "who has never seen the sea",
    "allergic to lies", "who talks to the dead", "with a price on their head",
    "who missed the last train home", "with a photographic memory",
    "who owes the wrong people", "back from the dead", "with a stolen face",
    "who can't feel pain", "sworn to silence", "with a map tattooed on their back",
    "running from a prophecy", "who never sleeps", "with a twin they've never met",
    "carrying a dead man's keys", "who lost a bet to a god",
    "with a suitcase full of secrets", "exiled for a crime they didn't commit",
    "who speaks to machines", "with a heart that ticks like a clock",
    "down to their last match", "who forgot their own name",
    "with a grudge older than the town", "looking for a way back",
    "who can't be photographed", "with a debt that won't die",
    "born during an eclipse", "who buried the wrong body",
    "with a one-way ticket", "halfway through a vow of silence",
    "who answers to no one",
]

# --------------------------------------------------------------------------- #
#  Locations  (each carries a SETTING: sea / space / urban / gothic / rural)
# --------------------------------------------------------------------------- #
LOC_ADJ = [
    "flooded", "abandoned", "neon-lit", "snowbound", "sun-bleached",
    "crumbling", "fog-drowned", "gilded", "underground", "floating",
    "haunted", "overgrown", "derelict", "glittering", "war-torn", "candlelit",
    "windswept", "smoke-filled", "rain-soaked", "moonlit", "half-built",
    "burning", "frozen", "sinking", "forgotten", "endless", "upside-down",
    "storm-battered", "sweltering", "ransacked", "mirror-walled", "ivy-choked",
    "lamplit", "ash-covered", "honeycombed", "salt-crusted", "blood-red",
    "humming", "collapsing", "sun-drenched", "dust-choked", "lantern-strung",
    "shadow-pooled", "rusted", "marble-floored", "wind-scoured", "moss-eaten",
    "starlit", "tilting", "boarded-up", "velvet-draped", "cavernous",
    "soot-blackened", "rain-slicked", "sunken", "wildflower-choked",
]
LOC_PLACES = [
    ("subway station", "urban"), ("monastery", "gothic"), ("casino", "urban"),
    ("lighthouse", "sea"), ("greenhouse", "rural"), ("opera house", "gothic"),
    ("oil rig", "sea"), ("night market", "urban"), ("border town", "rural"),
    ("space station", "space"), ("ferry", "sea"), ("roadside motel", "urban"),
    ("cathedral", "gothic"), ("salt mine", "rural"), ("amusement park", "urban"),
    ("radio tower", "urban"), ("swamp", "rural"), ("penthouse", "urban"),
    ("all-night diner", "urban"), ("observatory", "any"), ("submarine", "sea"),
    ("speakeasy", "urban"), ("train carriage", "urban"), ("rooftop garden", "urban"),
    ("morgue", "gothic"), ("aquarium", "sea"), ("bunker", "rural"),
    ("carnival", "any"), ("cable car", "urban"), ("wax museum", "gothic"),
    ("bath house", "urban"), ("hot-air balloon", "rural"), ("library", "any"),
    ("lighthouse keeper's cottage", "sea"), ("dive bar", "urban"),
    ("cargo freighter", "sea"), ("tidal cave", "sea"), ("fishing trawler", "sea"),
    ("coral reef", "sea"), ("harbor at low tide", "sea"),
    ("lunar colony", "space"), ("derelict starship", "space"),
    ("orbital greenhouse", "space"), ("asteroid mine", "space"),
    ("rooftop helipad", "urban"), ("subway tunnel", "urban"),
    ("parking garage", "urban"), ("laundromat", "urban"), ("art deco hotel", "urban"),
    ("pawn shop", "urban"), ("jazz club", "urban"), ("courthouse", "urban"),
    ("department store", "urban"), ("rooftop pool", "urban"),
    ("abbey ruins", "gothic"), ("crypt", "gothic"), ("manor house", "gothic"),
    ("clock tower", "gothic"), ("chapel", "gothic"), ("ossuary", "gothic"),
    ("ballroom", "gothic"), ("conservatory", "gothic"),
    ("cornfield", "rural"), ("cabin", "rural"), ("grain silo", "rural"),
    ("orchard", "rural"), ("desert highway", "rural"), ("mountain pass", "rural"),
    ("peat bog", "rural"), ("vineyard", "rural"), ("logging camp", "rural"),
    ("roadside chapel", "rural"), ("ghost town", "rural"), ("windmill", "rural"),
]
LOC_PLACE = [p for p, _ in LOC_PLACES]
LOC_SETTING = dict(LOC_PLACES)
LOC_TIME = [
    "at dawn", "after midnight", "during the last eclipse", "in the dead of winter",
    "on the eve of the festival", "as the tide comes in", "during a blackout",
    "in the middle of a heatwave", "at closing time", "as the storm rolls in",
    "on the longest night of the year", "just before the flood",
    "in the off-season", "the morning after the fire", "during the parade",
    "as the last train leaves", "under a blood moon", "at the stroke of noon",
    "during the harvest", "in the quiet before the raid", "on the day it never gets light",
    "as the carnival packs up", "during the drought", "the night the power returns",
    "as the fog rolls out", "on the anniversary", "at the turn of the tide",
    "in the last hour of the year", "while the bells are ringing",
    "as the comet passes",
]

# --------------------------------------------------------------------------- #
#  Actions  (each tagged with theme DOMAINS used for the genre logic-check)
# --------------------------------------------------------------------------- #
COOP_LINK = [
    "team up to", "join forces to", "conspire to", "reluctantly partner to",
    "set out together to", "make a pact to", "are forced to",
    "strike a deal to", "swear an oath to", "scheme together to",
    "band together to", "grudgingly agree to",
]
COOP_ACTION = [
    ("pull off one last heist", {"crime"}),
    ("rob a floating casino", {"crime"}),
    ("forge a dead king's will", {"crime", "mystery"}),
    ("crack an unbreakable vault", {"crime"}),
    ("fake their own deaths", {"crime", "comedy"}),
    ("smuggle a caged tiger across the border", {"crime", "adventure"}),
    ("launder a fortune in counterfeit art", {"crime"}),
    ("search for a missing god", {"supernatural", "adventure"}),
    ("steal back a stolen century", {"supernatural", "adventure"}),
    ("open the last door in the world", {"supernatural", "adventure"}),
    ("wake something that should stay asleep", {"supernatural", "horror"}),
    ("bury a machine that won't stay dead", {"scifi", "horror"}),
    ("outrun a rising tide", {"survival", "adventure"}),
    ("survive the longest night on record", {"survival", "horror"}),
    ("rebuild a sunken ship", {"adventure", "survival"}),
    ("find the edge of the map", {"adventure"}),
    ("chase a rumor to the end of the line", {"adventure", "mystery"}),
    ("rescue a kidnapped pop star", {"crime", "adventure"}),
    ("win a war they don't believe in", {"war"}),
    ("smuggle deserters past the front", {"war", "survival"}),
    ("decode a dead language", {"mystery"}),
    ("solve a murder before the snow melts", {"mystery", "crime"}),
    ("translate a message from the future", {"scifi"}),
    ("reboot a city that forgot itself", {"scifi"}),
    ("host a doomed dinner party", {"drama", "comedy"}),
    ("throw the perfect funeral", {"drama", "comedy"}),
    ("save a theater from closing", {"drama", "comedy"}),
    ("broadcast a forbidden song", {"drama", "romance"}),
    ("fall in love with the same stranger", {"romance", "comedy"}),
    ("plan a wedding nobody wants", {"romance", "comedy"}),
    ("deliver a coffin no one ordered", {"horror", "comedy"}),
    ("exorcise a very stubborn hotel", {"horror", "supernatural"}),
    ("hunt the thing in the walls", {"horror", "survival"}),
    ("plant a forest overnight", {"drama"}),
    ("talk a volcano out of erupting", {"survival", "comedy"}),
    ("escape a town that won't let them leave", {"horror", "mystery"}),
    ("settle a feud older than the county", {"drama", "violence"}),
    ("pull the perfect con on a crooked mayor", {"crime", "comedy"}),
    ("ferry refugees across a closing border", {"war", "drama"}),
    ("raise a creature they can't control", {"horror", "scifi"}),
]
CONFLICT_VERB = [
    ("duels", {"violence"}),
    ("hunts down", {"crime", "violence"}),
    ("schemes against", {"crime", "drama"}),
    ("double-crosses", {"crime"}),
    ("wages a quiet war on", {"war", "drama"}),
    ("competes with", {"drama", "comedy"}),
    ("plots revenge against", {"violence", "drama"}),
    ("faces off against", {"violence"}),
    ("betrays", {"crime", "drama"}),
    ("races", {"adventure"}),
    ("outwits", {"mystery", "comedy"}),
    ("bargains with", {"drama"}),
    ("haunts", {"supernatural", "horror"}),
    ("blackmails", {"crime"}),
    ("hunts", {"violence", "adventure"}),
    ("challenges", {"drama"}),
    ("stalks", {"horror", "crime"}),
    ("swindles", {"crime", "comedy"}),
    ("declares war on", {"war"}),
    ("interrogates", {"crime", "mystery"}),
    ("seduces and ruins", {"romance", "drama"}),
    ("frames", {"crime"}),
    ("out-duels", {"violence", "adventure"}),
    ("conspires against", {"crime", "drama"}),
    ("hexes", {"supernatural", "horror"}),
    ("undercuts", {"comedy", "drama"}),
    ("tracks across three states", {"crime", "adventure"}),
    ("squares off against", {"violence"}),
]
STAKE = [
    "an old debt", "a stolen relic", "the last ticket out", "her father's name",
    "a single bullet", "the only map that matters", "a forbidden recipe",
    "the deed to the moon", "a dead man's fortune", "the final word",
    "an unforgivable secret", "the throne", "a borrowed heart",
    "the last drop of fuel", "a promise neither will keep",
    "a city's water supply", "the cure that's left", "a confession",
    "the last honest vote", "a rigged election", "a child's inheritance",
    "the only working engine", "a name carved in stone", "the winning hand",
    "a sunken treasure", "the last seed bank", "a stolen identity",
    "the bridge out of town", "a hostage neither wants", "the recording",
    "a vial of antidote", "the keys to the kingdom", "a forged alibi",
    "the last lighthouse",
]
SOLO_LINK = [
    "sets out to", "is determined to", "secretly plans to", "risks everything to",
    "would do anything to", "spends the last of their luck trying to",
    "can't sleep until they", "has one night to", "vows to",
    "stakes their reputation to", "crosses the country to", "bargains away years to",
]
SOLO_ACTION = [
    ("find a way home", {"adventure", "drama"}),
    ("outrun an old curse", {"supernatural", "survival"}),
    ("deliver a letter that should never be read", {"mystery", "drama"}),
    ("steal back a lost name", {"mystery", "drama"}),
    ("bury a terrible secret", {"drama", "crime"}),
    ("track down a vanished god", {"supernatural", "mystery"}),
    ("win an impossible bet", {"comedy", "adventure"}),
    ("escape their own reflection", {"horror", "drama"}),
    ("catch a falling star before it lands", {"adventure"}),
    ("settle a hundred-year-old score", {"violence", "drama"}),
    ("talk a city out of burning", {"drama"}),
    ("teach a machine to dream", {"scifi"}),
    ("sell a lie big enough to save everyone", {"crime", "drama"}),
    ("find the one honest person left", {"mystery", "drama"}),
    ("out-stubborn the apocalypse", {"survival", "comedy"}),
    ("give death the slip one more time", {"supernatural", "survival"}),
    ("rob the only bank that still has gold", {"crime"}),
    ("solve the murder of their own double", {"mystery", "crime"}),
    ("crack a code hidden in a lullaby", {"mystery"}),
    ("survive a winter that won't end", {"survival", "horror"}),
    ("cross a desert on a single canteen", {"survival", "adventure"}),
    ("hunt the beast no one believes in", {"horror", "adventure"}),
    ("photograph a ghost before sunrise", {"supernatural", "horror"}),
    ("smuggle a confession out of the country", {"crime", "war"}),
    ("win back a love long given up", {"romance", "drama"}),
    ("ruin the man who ruined them", {"violence", "drama"}),
    ("decode a transmission from deep space", {"scifi", "mystery"}),
    ("escape a colony that owns their air", {"scifi", "survival"}),
    ("pull off the heist of the century alone", {"crime"}),
    ("make a tyrant laugh just once", {"comedy", "drama"}),
    ("walk into the storm to bring someone back", {"survival", "drama"}),
    ("break a spell with the wrong name", {"supernatural", "fantasy"}),
    ("outrun the law to the last border", {"crime", "adventure"}),
    ("win a duel they're sure to lose", {"violence", "drama"}),
    ("dig up what the flood left behind", {"mystery", "horror"}),
    ("trade a memory for a miracle", {"supernatural", "drama"}),
    ("invent an alibi the dead can't break", {"crime", "mystery"}),
    ("learn to love before the lights go out", {"romance", "drama"}),
    ("steer the last ship through the reef", {"adventure", "survival"}),
    ("forgive the unforgivable", {"drama"}),
]

# --------------------------------------------------------------------------- #
#  Genres  ->  (allowed SETTINGS, theme DOMAINS).  "any" = no restriction.
# --------------------------------------------------------------------------- #
ANY = {"any"}
GENRE_INFO = {
    # name: (allowed SETTINGS, theme DOMAINS, mood CATEGORY).  "any" = no limit.
    # --- crime --------------------------------------------------------------
    "film noir": ({"urban", "gothic"}, {"crime", "mystery", "drama"}, "crime"),
    "neo-noir thriller": ({"urban"}, {"crime", "mystery"}, "crime"),
    "hardboiled detective story": ({"urban"}, {"crime", "mystery"}, "crime"),
    "heist thriller": ({"urban"}, {"crime"}, "crime"),
    "crime saga": ({"urban", "rural"}, {"crime", "drama", "violence"}, "crime"),
    "gangster epic": ({"urban"}, {"crime", "violence", "drama"}, "crime"),
    "prison drama": ({"urban"}, {"crime", "drama", "survival"}, "crime"),
    "prison-break thriller": ({"urban"}, {"crime", "survival", "adventure"}, "crime"),
    "spy thriller": ({"urban"}, {"crime", "war", "mystery"}, "crime"),
    "espionage drama": ({"urban"}, {"crime", "war", "drama"}, "crime"),
    "political thriller": ({"urban"}, {"crime", "drama", "mystery"}, "crime"),
    # --- mystery ------------------------------------------------------------
    "cozy mystery": ({"rural", "urban"}, {"mystery"}, "mystery"),
    "locked-room mystery": ({"gothic", "urban"}, {"mystery", "crime"}, "mystery"),
    "whodunit": ({"gothic", "urban", "rural"}, {"mystery", "crime"}, "mystery"),
    "courtroom drama": ({"urban"}, {"drama", "mystery"}, "mystery"),
    "courtroom thriller": ({"urban"}, {"crime", "mystery", "drama"}, "mystery"),
    "giallo": ({"urban", "gothic"}, {"horror", "mystery", "crime"}, "mystery"),
    "psychological thriller": (ANY, {"mystery", "horror", "drama"}, "mystery"),
    "noir mystery": ({"urban", "gothic"}, {"crime", "mystery"}, "mystery"),
    # --- horror -------------------------------------------------------------
    "cosmic horror": (ANY, {"horror", "supernatural"}, "horror"),
    "gothic horror": ({"gothic", "rural"}, {"horror", "supernatural"}, "horror"),
    "folk horror": ({"rural", "gothic"}, {"horror", "supernatural"}, "horror"),
    "psychological horror": ({"urban", "gothic"}, {"horror", "mystery", "drama"}, "horror"),
    "body horror": ({"urban", "gothic"}, {"horror", "scifi"}, "horror"),
    "found-footage horror": (ANY, {"horror", "survival"}, "horror"),
    "haunted-house horror": ({"gothic"}, {"horror", "supernatural"}, "horror"),
    "slasher": ({"rural", "urban"}, {"horror", "violence"}, "horror"),
    "creature feature": ({"sea", "rural", "gothic", "space"}, {"horror", "survival"}, "horror"),
    "monster movie": ({"sea", "rural", "urban"}, {"horror", "adventure"}, "horror"),
    "survival horror": ({"rural", "sea", "space"}, {"horror", "survival"}, "horror"),
    "zombie apocalypse": ({"urban", "rural"}, {"horror", "survival"}, "horror"),
    "occult thriller": ({"urban", "gothic"}, {"horror", "supernatural", "mystery"}, "horror"),
    "surreal horror": (ANY, {"horror", "supernatural"}, "horror"),
    "fairy-tale horror": ({"gothic", "rural"}, {"horror", "supernatural", "fantasy"}, "horror"),
    # --- supernatural -------------------------------------------------------
    "ghost story": ({"gothic", "sea", "rural"}, {"supernatural", "horror"}, "supernatural"),
    "vampire romance": ({"gothic", "urban"}, {"supernatural", "romance", "horror"}, "supernatural"),
    "gothic romance": ({"gothic"}, {"romance", "supernatural", "drama"}, "supernatural"),
    "haunting melodrama": ({"gothic", "rural"}, {"supernatural", "drama", "romance"}, "supernatural"),
    # --- fantasy ------------------------------------------------------------
    "dark fairy tale": ({"gothic", "rural", "sea"}, {"supernatural", "horror", "fantasy"}, "fantasy"),
    "fairy tale": ({"gothic", "rural", "sea"}, {"supernatural", "adventure", "fantasy"}, "fantasy"),
    "fantasy quest": ({"rural", "gothic", "sea"}, {"adventure", "supernatural", "fantasy"}, "fantasy"),
    "sword and sorcery": ({"rural", "gothic"}, {"adventure", "violence", "fantasy"}, "fantasy"),
    "mythic epic": ({"rural", "sea", "gothic"}, {"adventure", "supernatural", "fantasy"}, "fantasy"),
    "magical adventure": (ANY, {"adventure", "supernatural", "fantasy"}, "fantasy"),
    "high fantasy": ({"rural", "gothic"}, {"adventure", "fantasy", "supernatural"}, "fantasy"),
    "urban fantasy": ({"urban"}, {"supernatural", "fantasy", "mystery"}, "fantasy"),
    "portal fantasy": (ANY, {"adventure", "fantasy", "supernatural"}, "fantasy"),
    # --- scifi --------------------------------------------------------------
    "space opera": ({"space"}, {"scifi", "adventure", "war"}, "scifi"),
    "alien invasion": (ANY, {"scifi", "survival", "horror"}, "scifi"),
    "cyberpunk noir": ({"urban", "space"}, {"scifi", "crime", "mystery"}, "scifi"),
    "steampunk adventure": ({"urban", "sea"}, {"scifi", "adventure"}, "scifi"),
    "time-travel thriller": (ANY, {"scifi", "mystery"}, "scifi"),
    "dystopian satire": ({"urban", "space"}, {"scifi", "drama", "comedy"}, "scifi"),
    "post-apocalyptic survival": ({"rural", "urban"}, {"survival", "scifi", "drama"}, "scifi"),
    "hard sci-fi": ({"space"}, {"scifi", "drama", "mystery"}, "scifi"),
    "space western": ({"space", "rural"}, {"scifi", "adventure", "violence"}, "scifi"),
    "eco-thriller": ({"sea", "rural"}, {"survival", "drama", "scifi"}, "scifi"),
    # --- adventure / western ------------------------------------------------
    "spaghetti western": ({"rural"}, {"violence", "adventure"}, "adventure"),
    "neo-western": ({"rural", "urban"}, {"crime", "violence", "drama"}, "adventure"),
    "weird western": ({"rural"}, {"supernatural", "violence", "horror"}, "adventure"),
    "revisionist western": ({"rural"}, {"violence", "drama", "adventure"}, "adventure"),
    "swashbuckler": ({"sea", "rural"}, {"adventure", "violence", "romance"}, "adventure"),
    "pirate adventure": ({"sea"}, {"adventure", "violence"}, "adventure"),
    "pulp adventure": (ANY, {"adventure", "violence"}, "adventure"),
    "treasure hunt": ({"sea", "rural"}, {"adventure", "mystery"}, "adventure"),
    "lost-world adventure": ({"rural", "sea"}, {"adventure", "survival"}, "adventure"),
    "jungle adventure": ({"rural"}, {"adventure", "survival"}, "adventure"),
    "samurai epic": ({"rural"}, {"violence", "drama", "adventure"}, "adventure"),
    "disaster epic": (ANY, {"survival", "adventure"}, "adventure"),
    "disaster thriller": (ANY, {"survival", "drama"}, "adventure"),
    # --- drama --------------------------------------------------------------
    "kitchen-sink drama": ({"urban", "rural"}, {"drama"}, "drama"),
    "coming-of-age drama": ({"urban", "rural", "sea"}, {"drama", "romance"}, "drama"),
    "family saga": ({"rural", "urban"}, {"drama"}, "drama"),
    "Southern gothic": ({"rural", "gothic"}, {"drama", "horror"}, "drama"),
    "sports drama": ({"urban"}, {"drama"}, "drama"),
    "medical drama": ({"urban"}, {"drama"}, "drama"),
    "road movie": ({"rural", "urban"}, {"adventure", "drama"}, "drama"),
    "revenge tragedy": (ANY, {"violence", "drama"}, "drama"),
    "prestige biopic": ({"urban", "rural"}, {"drama"}, "drama"),
    # --- romance ------------------------------------------------------------
    "epistolary romance": (ANY, {"romance", "drama"}, "romance"),
    "romantic tragedy": (ANY, {"romance", "drama"}, "romance"),
    "musical melodrama": ({"urban", "gothic"}, {"romance", "drama"}, "romance"),
    "forbidden romance": (ANY, {"romance", "drama"}, "romance"),
    "period romance": ({"gothic", "rural", "urban"}, {"romance", "drama"}, "romance"),
    # --- war ----------------------------------------------------------------
    "war epic": ({"rural", "urban"}, {"war", "drama"}, "war"),
    "war drama": ({"rural", "urban"}, {"war", "drama", "survival"}, "war"),
    "trench thriller": ({"rural"}, {"war", "survival", "drama"}, "war"),
    "resistance thriller": ({"urban", "rural"}, {"war", "crime", "drama"}, "war"),
    # --- weird --------------------------------------------------------------
    "surrealist fantasy": (ANY, ANY, "weird"),
    "magical realism": (ANY, ANY, "weird"),
    "weird fiction": (ANY, ANY, "weird"),
    "fable": (ANY, ANY, "weird"),
    "dream-logic fantasia": (ANY, ANY, "weird"),
    # --- comedy (deliberately deep + weighted up so it shows often) ----------
    "screwball comedy": ({"urban"}, {"comedy", "romance"}, "comedy"),
    "romantic comedy": ({"urban"}, {"comedy", "romance"}, "comedy"),
    "buddy comedy": ({"urban", "rural"}, {"comedy", "adventure"}, "comedy"),
    "dark comedy": ({"urban"}, {"comedy", "crime", "drama"}, "comedy"),
    "noir comedy": ({"urban"}, {"crime", "comedy", "mystery"}, "comedy"),
    "screwball noir": ({"urban"}, {"comedy", "crime", "mystery"}, "comedy"),
    "spy comedy": ({"urban"}, {"crime", "comedy"}, "comedy"),
    "heist comedy": ({"urban"}, {"crime", "comedy"}, "comedy"),
    "heist caper": ({"urban"}, {"crime", "comedy"}, "comedy"),
    "coming-of-age comedy": ({"urban", "rural"}, {"comedy", "drama", "romance"}, "comedy"),
    "mockumentary": (ANY, {"comedy"}, "comedy"),
    "absurdist tragicomedy": (ANY, {"comedy", "drama"}, "comedy"),
    "picaresque adventure": (ANY, {"adventure", "comedy"}, "comedy"),
    "musical comedy": ({"urban", "gothic"}, {"comedy", "romance"}, "comedy"),
    "slapstick farce": (ANY, {"comedy"}, "comedy"),
    "satire": ({"urban"}, {"comedy", "drama"}, "comedy"),
    "workplace comedy": ({"urban"}, {"comedy", "drama"}, "comedy"),
    "comedy of errors": (ANY, {"comedy", "romance"}, "comedy"),
    "fish-out-of-water comedy": (ANY, {"comedy", "adventure"}, "comedy"),
    "deadpan comedy": ({"urban", "rural"}, {"comedy", "drama"}, "comedy"),
    "stoner comedy": ({"urban"}, {"comedy"}, "comedy"),
}
GENRE = list(GENRE_INFO.keys())
GENRE_TONE = [
    "slow-burn", "melancholic", "unhinged", "tender", "baroque", "deadpan",
    "feverish", "lush", "bone-dry", "dreamlike", "razor-sharp", "gothic",
    "sun-drenched", "claustrophobic", "tongue-in-cheek", "operatic",
    "neon-soaked", "wintry", "hallucinatory", "hushed", "rain-soaked",
    "fever-bright", "brooding", "giddy", "sepia-toned", "blood-soaked",
    "wide-eyed", "world-weary", "candlelit", "high-contrast", "ice-cold",
    "swooning", "paranoid", "elegiac", "pulpy", "shadow-heavy", "windswept",
    "velvet", "moonstruck", "sun-faded", "",  # "" => no tone sometimes
]
GENRE_SETTINGS = {g: s for g, (s, _d, _c) in GENRE_INFO.items()}

# Mood balance: pick a CATEGORY first (so the many dark genres can't crowd out
# lighter ones), then a genre within it. Equal weights = balanced moods; comedy
# is boosted so it shows up clearly more often (the others stay even).
CATEGORIES = {}
for _g, (_s, _d, _c) in GENRE_INFO.items():
    CATEGORIES.setdefault(_c, []).append(_g)
CATEGORY_WEIGHTS = {"comedy": 3.0}      # everything else defaults to 1.0
_CAT_LIST = list(CATEGORIES.keys())
_CAT_W = [CATEGORY_WEIGHTS.get(c, 1.0) for c in _CAT_LIST]


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def _article(phrase):
    low = phrase.lower()
    if low.startswith(("one", "uni", "use", "eu", "ewe")):
        return "a"
    return "an" if low[:1] in "aeiou" else "a"


def _noun_fits(noun, domains):
    nd = CHAR_NOUN_DOMAINS.get(noun, {"any"})
    return "any" in nd or bool(nd & domains)


def _character(domains=None, exclude=None):
    pool = CHAR_NOUN
    if domains and "any" not in domains:
        compat = [n for n in CHAR_NOUN if _noun_fits(n, domains)]
        if compat:
            pool = compat
    for _ in range(12):
        core = f"{random.choice(CHAR_ADJ)} {random.choice(pool)}"
        c = f"{_article(core)} {core}"
        if random.random() < 0.5:
            c += " " + random.choice(CHAR_ORIGIN)
        if c != exclude:
            return c
    return c


def _fits(place, allowed):
    s = LOC_SETTING.get(place, "any")
    return "any" in allowed or s == "any" or s in allowed


def _location(allowed=None):
    """Pick a location whose SETTING is logical for the genre."""
    places = LOC_PLACE
    if allowed and "any" not in allowed:
        compat = [pl for pl in LOC_PLACE if _fits(pl, allowed)]
        if compat:
            places = compat
    place = random.choice(places)
    core = f"{random.choice(LOC_ADJ)} {place}"
    loc = f"{_article(core)} {core}"
    if random.random() < 0.55:
        loc += " " + random.choice(LOC_TIME)
    return loc


def _pick_action(pool, domains):
    """Pick an action whose theme DOMAINS are semantically consistent with the
    genre's domains (the heuristic semantic check). Falls back to the full pool
    if nothing matches, so it never fails."""
    if not domains or "any" in domains:
        return random.choice(pool)[0]
    compat = [a for a in pool if "any" in a[1] or (a[1] & domains)]
    return random.choice(compat or pool)[0]


def _genre():
    """Return (display genre with optional tone, base genre for lookups).
    Balanced by mood: a category is chosen first (comedy weighted up), then a
    genre within it — so the many dark genres can't crowd out the lighter ones."""
    cat = random.choices(_CAT_LIST, weights=_CAT_W, k=1)[0]
    base = random.choice(CATEGORIES[cat])
    tone = random.choice(GENRE_TONE)
    return f"{tone} {base}".strip(), base


def generate():
    """Return (sentence, parts) — a coherent random creative-writing prompt.
    The location fits the genre's setting and the action fits its domains."""
    genre, base = _genre()
    settings, domains, _cat = GENRE_INFO.get(base, (ANY, ANY, "weird"))
    h1 = _character(domains)
    loc = _location(settings)
    parts = {"hero1": h1, "hero2": None, "location": loc, "genre": genre}

    # equal ~1/3 each: one hero (solo), two heroes together, two heroes against
    rel = random.choice(("solo", "with", "against"))
    parts["relation"] = rel
    if rel == "solo":
        link = random.choice(SOLO_LINK)
        action = _pick_action(SOLO_ACTION, domains)
        parts["action"] = action
        core = f"{h1} {link} {action}"
    elif rel == "with":
        h2 = _character(domains, exclude=h1)
        parts["hero2"] = h2
        link = random.choice(COOP_LINK)
        action = _pick_action(COOP_ACTION, domains)
        parts["action"] = action
        core = f"{h1} and {h2} {link} {action}"
    else:  # against
        h2 = _character(domains, exclude=h1)
        parts["hero2"] = h2
        verb = _pick_action(CONFLICT_VERB, domains)
        stake = random.choice(STAKE)
        parts["action"] = f"{verb} over {stake}"
        core = f"{h1} {verb} {h2} over {stake}"

    text = f"{core}, in {loc}, in the mood and style of {genre}."
    text = text[0].upper() + text[1:]
    return text, parts


if __name__ == "__main__":          # quick manual sample + stats
    for _ in range(10):
        print("-", generate()[0])
    chars = len(CHAR_ADJ) * len(CHAR_NOUN) * (len(CHAR_ORIGIN) + 1)
    locs = len(LOC_ADJ) * len(LOC_PLACE) * (len(LOC_TIME) + 1)
    print(f"\nbanks: {len(CHAR_ADJ)} adj x {len(CHAR_NOUN)} nouns "
          f"({len(CHAR_ROLE)} jobs + {len(CHAR_TYPE)} types) -> "
          f"{chars:,} characters; {locs:,} locations; "
          f"{len(GENRE)} genres x {len(GENRE_TONE)} tones.")
