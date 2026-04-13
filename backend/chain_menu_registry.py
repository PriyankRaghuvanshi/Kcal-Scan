from __future__ import annotations

import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from chain_registry import resolve_chain_identity

try:
    from chain_menu_ingestion import get_chain_items_for_registry
except ImportError:
    get_chain_items_for_registry = None


CHAIN_MENU_REGISTRY_VERSION = "v1"
DEFAULT_COUNTRY_CODE = ""

# Coverage architecture: chains can be global, regional, or local
# Optional in JSON: coverage_type (global_chain|regional_chain|local_chain), markets (["AU","US"])
# When absent, inferred: country_code=GLOBAL -> global_chain; else regional_chain
COVERAGE_TYPES = ("global_chain", "regional_chain", "local_chain")

# Exposed source token for downstream preference logic.
# This is deterministic seeded data (not scraped live here).
_CHAIN_MENU_SOURCE = "chain_registry"
_CHAIN_EXTRACTION_METHOD = "chain_registry_official_menu"
_CHAIN_PARSE_METHOD = "chain_registry_seed"
_CHAIN_PARSED_VIA = "chain_registry"

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_WORD_RE = re.compile(r"[a-z0-9]+")
_NON_ASCII_APOSTROPHES = {"'", "\u2019", "\u2018", "`"}
_SEPARATOR_SPLIT_RE = re.compile(r"\s*(?:[-\u2013\u2014|,/]| at )\s*", re.IGNORECASE)

_LEADING_LOCATION_TOKENS = {
    "westfield",
    "food",
    "court",
    "mall",
    "plaza",
    "centre",
    "center",
    "station",
    "airport",
    "terminal",
    "level",
}

_TRAILING_LOCATION_TOKENS = {
    "store",
    "outlet",
    "branch",
    "shop",
    "kiosk",
    "food",
    "court",
    "mall",
    "plaza",
    "centre",
    "center",
    "station",
    "airport",
    "terminal",
    "nsw",
    "vic",
    "qld",
    "wa",
    "sa",
    "tas",
    "nt",
    "act",
    "au",
    "australia",
}

_CHAIN_ABBREVIATIONS = {
    "hj": "hungry jacks",
    "gyg": "guzman y gomez",
}

_COUNTRY_ALIASES = {
    "au": "AU",
    "australia": "AU",
    "us": "US",
    "usa": "US",
    "united states": "US",
    "uk": "GB",
    "great britain": "GB",
    "united kingdom": "GB",
    "nz": "NZ",
    "new zealand": "NZ",
    "in": "IN",
    "india": "IN",
    "global": "GLOBAL",
}

# Simple alias matcher for Supabase-backed chain rollout (Chipotle, Faasos, etc.)
CHAIN_KEYS: Dict[str, List[str]] = {
    "subway": ["subway", "subway restaurant"],
    "grilld": ["grilld", "grill'd"],
    "oporto": ["oporto"],
    "boost_juice": ["boost juice", "boost juice bars", "boost"],
    "guzman_y_gomez": ["guzman y gomez", "gyg"],
    "zambrero": ["zambrero"],
    "mcdonalds": ["mcdonalds", "mcdonald's", "mcdonald's", "maccas", "macca's", "macca's"],
    "hungry_jacks": ["hungry jacks", "hungry jack's", "hungry jack's", "hjs", "hj's"],
    "kfc": ["kfc", "kentucky fried chicken"],
    "burger_king": ["burger king", "bk", "burgerking"],
    "wendys": ["wendys", "wendy's"],
    "dominos": ["dominos", "domino's", "domino pizza", "dominos pizza"],
    "pizza_hut": ["pizza hut", "pizzahut"],
    "red_rooster": ["red rooster"],
    "nandos": ["nandos", "nando's", "nando's"],
    "chipotle": ["chipotle", "chipotle mexican grill"],
    "cava": ["cava", "cava grill", "cava mezze grill"],
    "chick_fil_a": ["chick-fil-a", "chick fil a", "chickfila"],
    "taco_bell": ["taco bell", "tacobell"],
    "panera": ["panera", "panera bread", "panera bread bakery cafe"],
    "starbucks": ["starbucks", "starbucks coffee"],
    "sweetgreen": ["sweetgreen", "sweet green"],
    "eatfit": ["eatfit", "eat fit"],
    "faasos": ["faasos", "faasos wraps", "faasos by eatsure"],
    "freshmenu": ["freshmenu", "fresh menu"],
    "behrouz_biryani": ["behrouz biryani", "behrouz", "behrouzbiryani", "behrouz biryani by oven story"],
    "wow_momo": ["wow momo", "wow! momo", "wowmomo"],
    "haldirams": ["haldirams", "haldiram's", "haldiram's", "haldiram"],
    "barbeque_nation": ["barbeque nation", "bbq nation", "barbequenation"],
    "a_and_w": ["a&w", "a and w"],
    "al_baik": ["al baik"],
    "arbys": ["arbys"],
    "baskin_robbins": ["baskin robbins"],
    "bbq_chicken": ["bbq chicken"],
    "betty_burgers": ["betty burgers"],
    "bikanervala": ["bikanervala"],
    "bobs": ["bob's", "bobs"],
    "boston_market": ["boston market"],
    "box8": ["box8"],
    "chai_point": ["chai point"],
    "chicken_licken": ["chicken licken"],
    "chowking": ["chowking"],
    "coco_ichibanya": ["coco ichibanya", "cocoichi"],
    "cosi": ["cosi"],
    "costa": ["costa", "costa coffee"],
    "cracker_barrel": ["cracker barrel"],
    "culvers": ["culvers"],
    "debonairs": ["debonairs"],
    "dennys": ["dennys"],
    "dunkin": ["dunkin"],
    "el_pollo_loco": ["el pollo loco"],
    "firehouse_subs": ["firehouse subs"],
    "fishbowl": ["fishbowl"],
    "five_guys": ["five guys"],
    "flunch": ["flunch"],
    "franco_manca": ["franco manca"],
    "freshii": ["freshii"],
    "freshness_burger": ["freshness burger"],
    "giraffas": ["giraffas"],
    "greenwich": ["greenwich"],
    "greggs": ["greggs"],
    "habib_s": ["habib s"],
    "hardees": ["hardee's", "hardees"],
    "harveys": ["harvey's", "harveys"],
    "ihop": ["ihop"],
    "in_n_out": ["in n out"],
    "itsu": ["itsu"],
    "jack_in_the_box": ["jack in the box"],
    "jason_deli": ["jason deli"],
    "jersey_mikes": ["jersey mikes"],
    "jollibee": ["jollibee"],
    "kyochon": ["kyochon"],
    "leon": ["leon"],
    "licious": ["licious"],
    "little_caesars": ["little caesars"],
    "lotteria": ["lotteria"],
    "mad_mex": ["mad mex"],
    "mary_browns": ["mary brown's", "mary browns"],
    "matsuya": ["matsuya"],
    "mod_pizza": ["mod pizza"],
    "mos_burger": ["mos burger"],
    "moti_mahal": ["moti mahal"],
    "natural_icecream": ["natural icecream"],
    "noodles_co": ["noodles co"],
    "nordsee": ["nordsee"],
    "panda_express": ["panda express"],
    "papa_johns": ["papa johns"],
    "paradise_biryani": ["paradise biryani", "paradise"],
    "paul": ["paul"],
    "pizza_express": ["pizza express"],
    "popeyes": ["popeyes"],
    "portillos": ["portillos"],
    "pret": ["pret a manger", "pret"],
    "qdoba": ["qdoba"],
    "quick": ["quick"],
    "raising_canes": ["raising canes"],
    "rebel_foods": ["rebel foods"],
    "saravana_bhavan": ["saravana bhavan"],
    "schnitz": ["schnitz"],
    "shake_shack": ["shake shack"],
    "shawarma_press": ["shawarma press"],
    "sonic": ["sonic"],
    "soul_origin": ["soul origin"],
    "steers": ["steers"],
    "stuff_d": ["stuff d"],
    "sukiya": ["sukiya"],
    "sushi_hub": ["sushi hub"],
    "sushi_sushi": ["sushi sushi"],
    "swiss_chalet": ["swiss chalet"],
    "texas_chicken": ["texas chicken"],
    "tim_hortons": ["tim hortons", "tims"],
    "tortilla": ["tortilla"],
    "tropical_smoothie": ["tropical smoothie"],
    "vapiano": ["vapiano"],
    "wagamama": ["wagamama"],
    "wasabi": ["wasabi"],
    "whataburger": ["whataburger"],
    "wingstop": ["wingstop"],
    "ya_kun": ["ya kun"],
    "yoshinoya": ["yoshinoya"],
    "zaxbys": ["zaxbys"],

    # --- Wave 1 bulk add: ingested chains with safe multi-token aliases ---
    "hyderabad_biryani_house": ["hyderabad biryani house"],
    "abs_absolute_barbecues": ["abs absolute barbecues", "absolute barbecues"],
    "dindigul_thalappakatti": ["dindigul thalappakatti"],
    "romanos_macaroni_grill": ["romanos macaroni grill"],
    "old_town_white_coffee": ["old town white coffee", "town white coffee"],
    "rawat_mishtan_bhandar": ["rawat mishtan bhandar"],
    "the_chicken_rice_shop": ["the chicken rice shop", "chicken rice shop"],
    "bourke_street_bakery": ["bourke street bakery"],
    "goila_butter_chicken": ["goila butter chicken"],
    "bengali_sweet_house": ["bengali sweet house"],
    "casper_and_gambinis": ["casper and gambinis"],
    "chicken_salad_chick": ["chicken salad chick"],
    "lucknowi_biryani_co": ["lucknowi biryani co"],
    "sigree_global_grill": ["sigree global grill"],
    "teriyaki_experience": ["teriyaki experience"],
    "veer_ji_malai_chaap": ["veer ji malai chaap"],
    "6_ballygunge_place": ["6 ballygunge place", "ballygunge place"],
    "buffalo_wild_wings": ["buffalo wild wings"],
    "cafe_delhi_heights": ["cafe delhi heights"],
    "california_burrito": ["california burrito"],
    "chargrill_charlies": ["chargrill charlies"],
    "cheesecake_factory": ["cheesecake factory"],
    "chooks_fresh_tasty": ["chooks fresh tasty"],
    "embassy_restaurant": ["embassy restaurant"],
    "fairgrounds_coffee": ["fairgrounds coffee"],
    "frankie_and_bennys": ["frankie and bennys"],
    "koramangala_social": ["koramangala social"],
    "michels_patisserie": ["michels patisserie"],
    "ministry_of_kebabs": ["ministry of kebabs"],
    "patisserie_valerie": ["patisserie valerie"],
    "sri_krishna_sweets": ["sri krishna sweets", "krishna sweets"],
    "teds_montana_grill": ["teds montana grill"],
    "the_bombay_canteen": ["the bombay canteen", "bombay canteen"],
    "ayam_geprek_bensu": ["ayam geprek bensu"],
    "belgian_waffle_co": ["belgian waffle co"],
    "boost_juice_au_v2": ["boost juice au v2"],
    "caribou_coffee_us": ["caribou coffee us"],
    "daves_hot_chicken": ["daves hot chicken"],
    "fosters_hollywood": ["fosters hollywood"],
    "long_john_silvers": ["long john silvers"],
    "lord_of_the_fries": ["lord of the fries"],
    "mahesh_lunch_home": ["mahesh lunch home"],
    "moolchand_parathe": ["moolchand parathe"],
    "moustache_escapes": ["moustache escapes"],
    "murugan_idli_shop": ["murugan idli shop"],
    "olivers_real_food": ["olivers real food"],
    "punjabi_by_nature": ["punjabi by nature"],
    "smokes_poutinerie": ["smokes poutinerie"],
    "sub_zero_nitrogen": ["sub zero nitrogen", "zero nitrogen"],
    "third_wave_coffee": ["third wave coffee"],
    "tkk_fried_chicken": ["tkk fried chicken", "fried chicken"],
    "zeus_street_greek": ["zeus street greek"],
    "5_and_dime_bagel": ["5 and dime bagel", "and dime bagel"],
    "barbeque_company": ["barbeque company"],
    "bhagat_tarachand": ["bhagat tarachand"],
    "bikkgane_biryani": ["bikkgane biryani"],
    "chicken_republic": ["chicken republic"],
    "east_side_marios": ["east side marios"],
    "fishermans_wharf": ["fishermans wharf"],
    "highlands_coffee": ["highlands coffee"],
    "highway_gomantak": ["highway gomantak"],
    "hogs_breath_cafe": ["hogs breath cafe"],
    "pans_and_company": ["pans and company"],
    "pizza_by_the_bay": ["pizza by the bay"],
    "ribs_and_burgers": ["ribs and burgers"],
    "richeese_factory": ["richeese factory"],
    "salsas_fresh_mex": ["salsas fresh mex"],
    "smoke_house_deli": ["smoke house deli"],
    "the_coffee_house": ["the coffee house", "coffee house"],
    "wahoos_fish_taco": ["wahoos fish taco"],
    "yellow_cab_pizza": ["yellow cab pizza"],
    "5_napkin_burger": ["5 napkin burger", "napkin burger"],
    "bhojohori_manna": ["bhojohori manna"],
    "biryani_by_kilo": ["biryani by kilo"],
    "cafe_coffee_day": ["cafe coffee day"],
    "checkers_rallys": ["checkers rallys"],
    "colonels_kababz": ["colonels kababz"],
    "cupcake_factory": ["cupcake factory"],
    "dakshin_express": ["dakshin express"],
    "di_bella_coffee": ["di bella coffee", "bella coffee"],
    "gregorys_coffee": ["gregorys coffee"],
    "joes_crab_shack": ["joes crab shack"],
    "mad_over_donuts": ["mad over donuts", "over donuts"],
    "manam_chocolate": ["manam chocolate"],
    "maxs_restaurant": ["maxs restaurant"],
    "mcalisters_deli": ["mcalisters deli"],
    "mellow_mushroom": ["mellow mushroom"],
    "mendocino_farms": ["mendocino farms"],
    "natraj_daribari": ["natraj daribari"],
    "nene_chicken_au": ["nene chicken au"],
    "new_york_minute": ["new york minute", "york minute"],
    "salt_water_cafe": ["salt water cafe"],
    "shrewsbury_pune": ["shrewsbury pune"],
    "student_biryani": ["student biryani"],
    "sweet_sensation": ["sweet sensation"],
    "texas_de_brazil": ["texas de brazil"],
    "texas_roadhouse": ["texas roadhouse"],
    "the_coffee_club": ["the coffee club", "coffee club"],
    "100_montaditos": ["100 montaditos"],
    "annas_taqueria": ["annas taqueria"],
    "bakers_delight": ["bakers delight"],
    "barbeque_pride": ["barbeque pride"],
    "bjs_restaurant": ["bjs restaurant"],
    "bonefish_grill": ["bonefish grill"],
    "britannia_cafe": ["britannia cafe"],
    "broadway_pizza": ["broadway pizza"],
    "bru_world_cafe": ["bru world cafe", "world cafe"],
    "burger_project": ["burger project"],
    "caribou_coffee": ["caribou coffee"],
    "chai_sutta_bar": ["chai sutta bar"],
    "chun_shui_tang": ["chun shui tang"],
    "copper_chimney": ["copper chimney"],
    "cote_brasserie": ["cote brasserie"],
    "crepes_waffles": ["crepes waffles"],
    "dhaba_junction": ["dhaba junction"],
    "goobne_chicken": ["goobne chicken"],
    "hard_rock_cafe": ["hard rock cafe"],
    "honest_burgers": ["honest burgers"],
    "house_of_candy": ["house of candy"],
    "jai_hind_dhaba": ["jai hind dhaba", "hind dhaba"],
    "johnny_rockets": ["johnny rockets"],
    "kailash_parbat": ["kailash parbat"],
    "karachi_bakery": ["karachi bakery"],
    "lazeez_affaire": ["lazeez affaire"],
    "mainland_china": ["mainland china"],
    "masala_library": ["masala library"],
    "mk_restaurants": ["mk restaurants"],
    "moes_southwest": ["moes southwest"],
    "natraj_aliwale": ["natraj aliwale"],
    "new_york_fries": ["new york fries", "york fries"],
    "pardos_chicken": ["pardos chicken"],
    "paris_baguette": ["paris baguette"],
    "pie_in_the_sky": ["pie in the sky", "in the sky"],
    "pizza_pilgrims": ["pizza pilgrims"],
    "pollo_tropical": ["pollo tropical"],
    "roadhouse_cafe": ["roadhouse cafe"],
    "tea_villa_cafe": ["tea villa cafe", "villa cafe"],
    "tous_les_jours": ["tous les jours"],
    "yazdani_bakery": ["yazdani bakery"],
    "aslam_chicken": ["aslam chicken"],
    "bahama_breeze": ["bahama breeze"],
    "biryani_blues": ["biryani blues"],
    "booster_juice": ["booster juice"],
    "brioche_doree": ["brioche doree"],
    "cafe_de_coral": ["cafe de coral"],
    "cafe_niloufer": ["cafe niloufer"],
    "chicago_pizza": ["chicago pizza"],
    "chicken_treat": ["chicken treat"],
    "corner_bakery": ["corner bakery"],
    "country_style": ["country style"],
    "don_belisario": ["don belisario"],
    "einstein_bros": ["einstein bros"],
    "fonda_mexican": ["fonda mexican"],
    "frozen_bottle": ["frozen bottle"],
    "garcias_pizza": ["garcias pizza"],
    "goli_vada_pav": ["goli vada pav"],
    "hans_im_gluck": ["hans im gluck"],
    "hotel_minerva": ["hotel minerva"],
    "indian_accent": ["indian accent"],
    "kahve_dunyasi": ["kahve dunyasi"],
    "kake_da_hotel": ["kake da hotel"],
    "kayani_bakery": ["kayani bakery"],
    "kwality_walls": ["kwality walls"],
    "la_mie_caline": ["la mie caline", "mie caline"],
    "la_piadineria": ["la piadineria"],
    "mast_kalandar": ["mast kalandar"],
    "meghana_foods": ["meghana foods"],
    "mucho_burrito": ["mucho burrito"],
    "old_wild_west": ["old wild west", "wild west"],
    "ole_and_steen": ["ole and steen", "and steen"],
    "opa_of_greece": ["opa of greece", "of greece"],
    "pind_balluchi": ["pind balluchi"],
    "punjabi_tadka": ["punjabi tadka"],
    "secret_recipe": ["secret recipe"],
    "smoothie_king": ["smoothie king"],
    "steak_n_shake": ["steak n shake"],
    "tavuk_dunyasi": ["tavuk dunyasi"],
    "tender_greens": ["tender greens"],
    "the_good_bowl": ["the good bowl", "good bowl"],
    "tijuana_flats": ["tijuana flats"],
    "wrap_and_roll": ["wrap and roll"],
    "amul_parlour": ["amul parlour"],
    "andhra_spice": ["andhra spice"],
    "auntie_annes": ["auntie annes"],
    "banh_mi_boys": ["banh mi boys"],
    "bella_italia": ["bella italia"],
    "black_rabbit": ["black rabbit"],
    "bobby_burger": ["bobby burger"],
    "bombay_chaat": ["bombay chaat"],
    "bombay_salsa": ["bombay salsa"],
    "boston_pizza": ["boston pizza"],
    "bucking_bull": ["bucking bull"],
    "burger_singh": ["burger singh"],
    "burgers_king": ["burgers king"],
    "chappan_bhog": ["chappan bhog"],
    "china_bistro": ["china bistro"],
    "chor_bizarre": ["chor bizarre"],
    "class_croute": ["class croute"],
    "coco_di_mama": ["coco di mama"],
    "corner_house": ["corner house"],
    "cousins_subs": ["cousins subs"],
    "cream_centre": ["cream centre"],
    "din_tai_fung": ["din tai fung", "tai fung"],
    "fogo_de_chao": ["fogo de chao"],
    "gails_bakery": ["gails bakery"],
    "gloria_jeans": ["gloria jeans"],
    "gozleme_king": ["gozleme king"],
    "hotel_shadab": ["hotel shadab"],
    "j_alexanders": ["j alexanders"],
    "jaffer_bhais": ["jaffer bhais"],
    "jamaica_blue": ["jamaica blue"],
    "juan_maestro": ["juan maestro"],
    "kream_kastle": ["kream kastle"],
    "krispy_kreme": ["krispy kreme"],
    "kyani_and_co": ["kyani and co"],
    "la_madeleine": ["la madeleine"],
    "la_porchetta": ["la porchetta"],
    "marcos_pizza": ["marcos pizza"],
    "masala_craft": ["masala craft"],
    "mecca_coffee": ["mecca coffee"],
    "mother_dairy": ["mother dairy"],
    "mrs_bakeshop": ["mrs bakeshop"],
    "muffin_break": ["muffin break"],
    "munch_bakery": ["munch bakery"],
    "nene_chicken": ["nene chicken"],
    "olive_bistro": ["olive bistro"],
    "olive_garden": ["olive garden"],
    "pana_organic": ["pana organic"],
    "papa_murphys": ["papa murphys"],
    "peets_coffee": ["peets coffee"],
    "philz_coffee": ["philz coffee"],
    "pizza_capers": ["pizza capers"],
    "pizza_napoli": ["pizza napoli"],
    "punjab_grill": ["punjab grill"],
    "punjab_sindh": ["punjab sindh"],
    "ruby_tuesday": ["ruby tuesday"],
    "sees_candies": ["sees candies"],
    "shanti_sagar": ["shanti sagar"],
    "shree_mithai": ["shree mithai"],
    "simit_sarayi": ["simit sarayi"],
    "south_indies": ["south indies"],
    "thai_express": ["thai express"],
    "tobys_estate": ["tobys estate"],
    "trung_nguyen": ["trung nguyen"],
    "veggie_grill": ["veggie grill"],
    "waffle_house": ["waffle house"],
    "wat_a_burger": ["wat a burger", "a burger"],
    "white_castle": ["white castle"],
    "woodside_inn": ["woodside inn"],
    "yazdani_cafe": ["yazdani cafe"],
    "800_degrees": ["800 degrees"],
    "99_pancakes": ["99 pancakes"],
    "alice_pizza": ["alice pizza"],
    "ask_italian": ["ask italian"],
    "bakery_cafe": ["bakery cafe"],
    "blaze_pizza": ["blaze pizza"],
    "blue_bottle": ["blue bottle"],
    "bombay_adda": ["bombay adda"],
    "bombay_blue": ["bombay blue"],
    "bombay_duck": ["bombay duck"],
    "burger_edge": ["burger edge"],
    "burger_farm": ["burger farm"],
    "burger_urge": ["burger urge"],
    "cactus_club": ["cactus club"],
    "crust_pizza": ["crust pizza"],
    "dairy_queen": ["dairy queen"],
    "delhi_zaika": ["delhi zaika"],
    "desi_punjab": ["desi punjab"],
    "es_teler_77": ["es teler 77", "teler 77"],
    "fasta_pasta": ["fasta pasta"],
    "first_watch": ["first watch"],
    "french_loaf": ["french loaf"],
    "greco_pizza": ["greco pizza"],
    "hotel_nayab": ["hotel nayab"],
    "j_co_donuts": ["j co donuts", "co donuts"],
    "jaho_coffee": ["jaho coffee"],
    "jimmy_johns": ["jimmy johns"],
    "kacchi_bhai": ["kacchi bhai"],
    "khan_chacha": ["khan chacha"],
    "konkan_cafe": ["konkan cafe"],
    "las_iguanas": ["las iguanas"],
    "mang_inasal": ["mang inasal"],
    "max_brenner": ["max brenner"],
    "max_burgers": ["max burgers"],
    "nudie_juice": ["nudie juice"],
    "oh_calcutta": ["oh calcutta"],
    "orange_leaf": ["orange leaf"],
    "pista_house": ["pista house"],
    "pita_pit_au": ["pita pit au"],
    "pita_pit_in": ["pita pit in"],
    "pizza_pizza": ["pizza pizza"],
    "poulet_reti": ["poulet reti"],
    "red_lobster": ["red lobster"],
    "sagar_ratna": ["sagar ratna"],
    "shah_ghouse": ["shah ghouse"],
    "shwe_pu_zun": ["shwe pu zun"],
    "slay_coffee": ["slay coffee"],
    "smokeys_bbq": ["smokeys bbq"],
    "smokin_joes": ["smokin joes"],
    "sweet_truth": ["sweet truth"],
    "tewari_bros": ["tewari bros"],
    "tgi_fridays": ["tgi fridays"],
    "the_counter": ["the counter"],
    "three_beans": ["three beans"],
    "wok_to_walk": ["wok to walk", "to walk"],
    "wow_chicken": ["wow chicken"],
    "16_handles": ["16 handles"],
    "85c_bakery": ["85c bakery"],
    "baja_fresh": ["baja fresh"],
    "blue_tokai": ["blue tokai"],
    "cafe_maure": ["cafe maure"],
    "caffe_nero": ["caffe nero"],
    "cali_press": ["cali press"],
    "captain_ds": ["captain ds"],
    "chai_patti": ["chai patti"],
    "chaina_ram": ["chaina ram"],
    "chiya_chai": ["chiya chai"],
    "cold_stone": ["cold stone"],
    "curry_leaf": ["curry leaf"],
    "donut_king": ["donut king"],
    "donut_time": ["donut time"],
    "dutch_bros": ["dutch bros"],
    "farzi_cafe": ["farzi cafe"],
    "freshii_us": ["freshii us"],
    "hell_pizza": ["hell pizza"],
    "hoka_bento": ["hoka bento"],
    "hot_breads": ["hot breads"],
    "java_house": ["java house"],
    "just_salad": ["just salad"],
    "kaati_zone": ["kaati zone"],
    "kura_sushi": ["kura sushi"],
    "la_colombe": ["la colombe"],
    "lot_burger": ["lot burger"],
    "manchu_wok": ["manchu wok"],
    "mojo_pizza": ["mojo pizza"],
    "moms_touch": ["moms touch"],
    "noodle_box": ["noodle box"],
    "o_charleys": ["o charleys"],
    "oven_story": ["oven story"],
    "ram_ashrey": ["ram ashrey"],
    "san_churro": ["san churro"],
    "second_cup": ["second cup"],
    "shiv_sagar": ["shiv sagar"],
    "star_kabab": ["star kabab"],
    "sukh_sagar": ["sukh sagar"],
    "sumo_salad": ["sumo salad"],
    "tea_trails": ["tea trails"],
    "wah_ji_wah": ["wah ji wah", "ji wah"],
    "which_wich": ["which wich"],
    "white_spot": ["white spot"],
    "after_you": ["after you"],
    "asia_haus": ["asia haus"],
    "beer_cafe": ["beer cafe"],
    "big_chill": ["big chill"],
    "bob_evans": ["bob evans"],
    "city_mart": ["city mart"],
    "cold_rock": ["cold rock"],
    "cook_door": ["cook door"],
    "el_corral": ["el corral"],
    "jimmy_boy": ["jimmy boy"],
    "pf_changs": ["pf changs"],
    "phuc_long": ["phuc long"],
    "pizza_inn": ["pizza inn"],
    "red_mango": ["red mango"],
    "red_robin": ["red robin"],
    "sushi_bay": ["sushi bay"],
    "the_habit": ["the habit"],
    "triple_os": ["triple os"],
    "wendys_au": ["wendys au"],
    "al_tazaj": ["al tazaj"],
    "carls_jr": ["carls jr"],
    "cook_out": ["cook out"],
    "del_taco": ["del taco"],
    "la_lucha": ["la lucha"],
    "la_pinoz": ["la pinoz"],
    "la_place": ["la place"],
    "mr_biggs": ["mr biggs"],
    "pie_face": ["pie face"],
    "pita_pit": ["pita pit"],
    "tai_hing": ["tai hing"],
    "tea_post": ["tea post"],
    "tsui_wah": ["tsui wah"],
    "us_pizza": ["us pizza"],
    "yo_sushi": ["yo sushi"],
    "naf_naf": ["naf naf"],
    "pei_wei": ["pei wei"],
    "the_keg": ["the keg"],
    "mr_sub": ["mr sub"],
    "oye_24": ["oye 24"],
    "pho_24": ["pho 24"],
    "rolld": ["roll'd", "rolld"],
}

_SUFFIX_RE = re.compile(
    r"\b(soma|times square|5th avenue|indiranagar|khar|salt lake|restaurant|restaurants|store|outlet|branch)\b",
    re.IGNORECASE,
)


def _normalize_chain_text(text: str) -> str:
    s = str(text or "").strip().lower()
    s = s.replace("\u2019", "'")
    s = re.sub(r"[^a-z0-9\s']", " ", s)
    s = _SUFFIX_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def match_chain_key(place_name: str, brand_hint: Optional[str] = None) -> Optional[str]:
    candidates = [_normalize_chain_text(brand_hint or ""), _normalize_chain_text(place_name or "")]
    candidates = [c for c in candidates if c]

    for candidate in candidates:
        for chain_key, aliases in CHAIN_KEYS.items():
            for alias in aliases:
                normalized_alias = _normalize_chain_text(alias)
                if candidate == normalized_alias or candidate.startswith(normalized_alias + " "):
                    return chain_key
    return None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    token = " ".join(str(raw).strip().split()).lower()
    return token in _TRUE_VALUES


def _coverage_path() -> Path:
    override = str(os.getenv("CHAIN_MENU_COVERAGE_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "chain_menu_coverage.json"


def _normalize_space(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_brand(value: Any) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    text = unicodedata.normalize("NFKD", raw)
    text = text.encode("ascii", "ignore").decode("ascii")
    for token in _NON_ASCII_APOSTROPHES:
        text = text.replace(token, "")
    text = text.replace("&", " and ")
    normalized = " ".join(_WORD_RE.findall(text.lower()))
    if normalized in _CHAIN_ABBREVIATIONS:
        return _CHAIN_ABBREVIATIONS[normalized]
    return normalized


def _tokenize_name(value: str) -> List[str]:
    return [token for token in _normalize_brand(value).split() if token]


def _strip_leading_location_tokens(tokens: List[str]) -> List[str]:
    out = list(tokens)
    while out and out[0] in _LEADING_LOCATION_TOKENS and len(out) > 1:
        out = out[1:]
    return out


def _strip_trailing_location_tokens(tokens: List[str]) -> List[str]:
    out = list(tokens)
    while out and len(out) > 1:
        tail = out[-1]
        if tail in _TRAILING_LOCATION_TOKENS:
            out = out[:-1]
            continue
        if tail.isdigit():
            out = out[:-1]
            continue
        if len(tail) == 1 and tail.isalpha():
            out = out[:-1]
            continue
        break
    return out


def _place_name_candidates(raw_place_name: Any) -> List[str]:
    base = str(raw_place_name or "").strip()
    if not base:
        return []

    segments = [base]
    paren_removed = re.sub(r"\([^)]*\)", " ", base)
    if paren_removed.strip():
        segments.append(paren_removed)
    segments.extend(_SEPARATOR_SPLIT_RE.split(base))

    out: List[str] = []
    seen = set()
    for segment in segments:
        norm = _normalize_brand(segment)
        if not norm:
            continue
        tokens = [token for token in norm.split() if token]
        if not tokens:
            continue

        variants: List[List[str]] = [tokens]
        trimmed = _strip_trailing_location_tokens(tokens)
        if trimmed != tokens:
            variants.append(trimmed)
        lead_trimmed = _strip_leading_location_tokens(tokens)
        if lead_trimmed != tokens:
            variants.append(lead_trimmed)
            variants.append(_strip_trailing_location_tokens(lead_trimmed))
        if len(tokens) >= 3:
            variants.append(tokens[:3])
            variants.append(tokens[:2])

        for parts in variants:
            candidate = " ".join(part for part in parts if part)
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            out.append(candidate)
    return out


def _normalize_country_code(value: Any) -> str:
    token = _normalize_space(value).lower()
    if not token:
        return ""
    if token in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[token]
    if len(token) == 2 and token.isalpha():
        return token.upper()
    return ""


def _infer_country_from_latlng(lat: Any, lng: Any) -> str:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return ""
    if lat_f == 0.0 and lng_f == 0.0:
        return ""
    # Rough bounding boxes. Address-based inference runs first; this is the fallback.
    # Ordered so overlapping regions (SG carve-out before MY; TH before MY; MY before ID)
    # resolve correctly.
    if 24.0 <= lat_f <= 49.5 and -125.0 <= lng_f <= -66.0:
        return "US"  # continental US
    if 18.0 <= lat_f <= 23.0 and -161.0 <= lng_f <= -154.0:
        return "US"  # Hawaii
    if 51.0 <= lat_f <= 72.0 and -169.0 <= lng_f <= -129.0:
        return "US"  # Alaska
    if -44.0 <= lat_f <= -10.0 and 113.0 <= lng_f <= 154.0:
        return "AU"
    if -47.5 <= lat_f <= -33.5 and 165.5 <= lng_f <= 179.5:
        return "NZ"
    # Nepal / Sri Lanka / Myanmar carved out before India (overlap).
    if 26.3 <= lat_f <= 30.5 and 80.1 <= lng_f <= 88.2:
        return "NP"
    if 5.9 <= lat_f <= 9.8 and 79.7 <= lng_f <= 81.9:
        return "LK"
    if 9.5 <= lat_f <= 28.5 and 92.2 <= lng_f <= 101.2:
        return "MM"
    if 6.5 <= lat_f <= 37.0 and 68.0 <= lng_f <= 98.0:
        return "IN"
    if 49.0 <= lat_f <= 61.0 and -9.0 <= lng_f <= 2.0:
        return "GB"
    # Singapore carve-out before Malaysia (SG is ~1.15-1.5°N, 103.5-104.1°E)
    if 1.15 <= lat_f <= 1.5 and 103.5 <= lng_f <= 104.1:
        return "SG"
    # Thailand (lat 5.5-20.5, lng 97.3-105.6); carve before MY to handle southern TH
    if 5.5 <= lat_f <= 20.5 and 97.3 <= lng_f <= 105.6:
        return "TH"
    # Malaysia peninsular + east (Sabah/Sarawak). Keep before Indonesia.
    if 0.8 <= lat_f <= 7.5 and 99.5 <= lng_f <= 119.3:
        return "MY"
    # Indonesia — catches most of archipelago south of equator
    if -11.0 <= lat_f <= 6.1 and 95.0 <= lng_f <= 141.0:
        return "ID"
    # Philippines
    if 4.5 <= lat_f <= 21.0 and 116.0 <= lng_f <= 127.0:
        return "PH"
    # Taiwan
    if 21.5 <= lat_f <= 25.5 and 119.5 <= lng_f <= 122.1:
        return "TW"
    # Hong Kong (tiny, carve before any future China box)
    if 22.15 <= lat_f <= 22.6 and 113.8 <= lng_f <= 114.45:
        return "HK"
    # Vietnam — south/central/north. Careful of Laos/Cambodia overlap but those aren't
    # in our bbox list.
    if 8.0 <= lat_f <= 23.5 and 102.0 <= lng_f <= 110.0:
        return "VN"
    # Italy — mainland + Sicily/Sardinia. Non-overlapping with FR/DE.
    if 35.5 <= lat_f <= 47.1 and 6.6 <= lng_f <= 18.5:
        return "IT"
    # Spain — mainland + Balearics. Careful: PT would overlap, not in list.
    if 35.8 <= lat_f <= 43.8 and -9.5 <= lng_f <= 4.3:
        return "ES"
    # Netherlands — small, fairly tight.
    if 50.7 <= lat_f <= 53.7 and 3.2 <= lng_f <= 7.3:
        return "NL"
    # Poland — central Europe.
    if 49.0 <= lat_f <= 55.0 and 14.1 <= lng_f <= 24.2:
        return "PL"
    # Germany — mostly non-overlapping with NL/PL if ordered correctly.
    if 47.3 <= lat_f <= 55.1 and 5.9 <= lng_f <= 15.0:
        return "DE"
    # France — mainland.
    if 41.3 <= lat_f <= 51.1 and -5.2 <= lng_f <= 9.6:
        return "FR"
    # Saudi Arabia.
    if 16.0 <= lat_f <= 32.5 and 34.5 <= lng_f <= 55.7:
        return "SA"
    # Turkey.
    if 35.9 <= lat_f <= 42.1 and 25.6 <= lng_f <= 44.8:
        return "TR"
    # Egypt.
    if 22.0 <= lat_f <= 31.7 and 25.0 <= lng_f <= 35.0:
        return "EG"
    # Kuwait.
    if 28.5 <= lat_f <= 30.1 and 46.5 <= lng_f <= 48.4:
        return "KW"
    # Qatar.
    if 24.5 <= lat_f <= 26.2 and 50.7 <= lng_f <= 51.7:
        return "QA"
    # Mexico — mostly south of US.
    if 14.5 <= lat_f <= 32.7 and -117.3 <= lng_f <= -86.7:
        return "MX"
    # LatAm (each clean, non-overlapping).
    if -55.0 <= lat_f <= -21.8 and -73.6 <= lng_f <= -53.6:
        return "AR"
    if -4.2 <= lat_f <= 12.5 and -79.0 <= lng_f <= -66.9:
        return "CO"
    if -55.9 <= lat_f <= -17.5 and -75.6 <= lng_f <= -66.9:
        return "CL"
    if -18.4 <= lat_f <= -0.04 and -81.3 <= lng_f <= -68.7:
        return "PE"
    # Africa.
    if 4.3 <= lat_f <= 13.9 and 2.7 <= lng_f <= 14.7:
        return "NG"
    if -4.7 <= lat_f <= 5.0 and 33.9 <= lng_f <= 41.9:
        return "KE"
    if 21.4 <= lat_f <= 35.9 and -17.0 <= lng_f <= -1.0:
        return "MA"
    # PK and BD deliberately NOT bbox'd — they overlap India too heavily.
    # Rely on address text inference for those markets.
    return ""


def _infer_country_code(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    for key in ("country_code", "countryCode", "country", "region", "locale_country"):
        candidate = _normalize_country_code(payload.get(key))
        if candidate:
            return candidate

    text = " ".join(
        [
            str(payload.get("address") or payload.get("vicinity") or ""),
            str(payload.get("formatted_address") or payload.get("formattedAddress") or ""),
        ]
    ).lower()
    if "australia" in text:
        return "AU"
    if "united states" in text or " usa" in f" {text} ":
        return "US"
    if "india" in text:
        return "IN"
    if "new zealand" in text:
        return "NZ"
    if "united kingdom" in text or " uk" in f" {text} ":
        return "GB"
    if "singapore" in text:
        return "SG"
    if "malaysia" in text:
        return "MY"
    if "thailand" in text:
        return "TH"
    if "indonesia" in text:
        return "ID"
    if "philippines" in text:
        return "PH"
    if "japan" in text:
        return "JP"
    if "canada" in text:
        return "CA"
    if "brazil" in text or "brasil" in text:
        return "BR"
    if "mexico" in text or "méxico" in text:
        return "MX"
    if "germany" in text or "deutschland" in text:
        return "DE"
    if "france" in text:
        return "FR"
    if "south africa" in text:
        return "ZA"
    if "united arab emirates" in text or " uae" in f" {text} ":
        return "AE"
    if "south korea" in text or "republic of korea" in text:
        return "KR"
    if "taiwan" in text:
        return "TW"
    if "hong kong" in text:
        return "HK"
    if "vietnam" in text or "viet nam" in text:
        return "VN"
    if "pakistan" in text:
        return "PK"
    if "bangladesh" in text:
        return "BD"
    if "italy" in text or "italia" in text:
        return "IT"
    if "spain" in text or "españa" in text or "espana" in text:
        return "ES"
    if "netherlands" in text or "holland" in text:
        return "NL"
    if "poland" in text or "polska" in text:
        return "PL"
    if "belgium" in text or "belgique" in text or "belgie" in text:
        return "BE"
    if "saudi arabia" in text or "ksa" in text:
        return "SA"
    if "turkey" in text or "türkiye" in text or "turkiye" in text:
        return "TR"
    if "egypt" in text or "misr" in text:
        return "EG"
    if "kuwait" in text:
        return "KW"
    if "qatar" in text:
        return "QA"
    if "argentina" in text:
        return "AR"
    if "colombia" in text:
        return "CO"
    if "chile" in text:
        return "CL"
    if "peru" in text or "perú" in text:
        return "PE"
    if "nigeria" in text:
        return "NG"
    if "kenya" in text:
        return "KE"
    if "morocco" in text or "maroc" in text:
        return "MA"
    if "sri lanka" in text:
        return "LK"
    if "nepal" in text:
        return "NP"
    if "myanmar" in text or "burma" in text:
        return "MM"

    latlng_guess = _infer_country_from_latlng(payload.get("lat"), payload.get("lng"))
    if latlng_guess:
        return latlng_guess
    return ""


@lru_cache(maxsize=1)
def _load_registry() -> Dict[str, Any]:
    path = _coverage_path()
    if not path.exists():
        return {"version": CHAIN_MENU_REGISTRY_VERSION, "chains": []}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {"version": CHAIN_MENU_REGISTRY_VERSION, "chains": []}

    if not isinstance(data, dict):
        return {"version": CHAIN_MENU_REGISTRY_VERSION, "chains": []}
    chains = data.get("chains")
    if not isinstance(chains, list):
        chains = []
    return {
        "version": str(data.get("version") or CHAIN_MENU_REGISTRY_VERSION),
        "chains": [row for row in chains if isinstance(row, dict)],
    }


def clear_chain_menu_registry_cache() -> None:
    _load_registry.cache_clear()


def _infer_coverage_type(entry: Dict[str, Any]) -> str:
    """Infer coverage_type from entry. Supports scalable expansion schema."""
    explicit = str(entry.get("coverage_type") or "").strip().lower()
    if explicit in COVERAGE_TYPES:
        return explicit
    country = _normalize_country_code(entry.get("country_code")) or "GLOBAL"
    return "global_chain" if country == "GLOBAL" else "regional_chain"


def list_chain_entries(
    country_code: str | None = None,
    include_global: bool = True,
    coverage_type: str | None = None,
) -> List[Dict[str, Any]]:
    """
    List chain entries. Supports scalable expansion:
    - country_code / include_global: legacy filter
    - coverage_type: optional filter by global_chain | regional_chain | local_chain
    """
    registry = _load_registry()
    rows = registry.get("chains") if isinstance(registry.get("chains"), list) else []
    requested_country = _normalize_country_code(country_code)
    req_coverage = str(coverage_type or "").strip().lower() if coverage_type else None

    out: List[Dict[str, Any]] = []
    for row in rows:
        r = dict(row)
        r["coverage_type"] = _infer_coverage_type(r)
        row_country = _normalize_country_code(r.get("country_code")) or "GLOBAL"
        if req_coverage and r["coverage_type"] != req_coverage:
            continue
        if requested_country:
            if row_country == requested_country:
                out.append(r)
            elif include_global and row_country == "GLOBAL":
                out.append(r)
        else:
            out.append(r)
    return out


def _entry_aliases(entry: Dict[str, Any]) -> List[str]:
    aliases = entry.get("chain_aliases") if isinstance(entry.get("chain_aliases"), list) else []
    out: List[str] = []
    seen = set()

    candidates = [entry.get("chain_name"), entry.get("chain_key")] + aliases
    for row in candidates:
        norm = _normalize_brand(row)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def _alias_match_score(place_candidate: str, alias_norm: str) -> float:
    if not place_candidate or not alias_norm:
        return 0.0

    if place_candidate == alias_norm:
        return 1.0

    place_tokens = place_candidate.split()
    alias_tokens = alias_norm.split()

    if alias_tokens and place_tokens[: len(alias_tokens)] == alias_tokens:
        suffix_count = len(place_tokens) - len(alias_tokens)
        suffix_penalty = 0.02 * min(5, max(0, suffix_count))
        return max(0.84, 0.98 - suffix_penalty)

    if alias_tokens and len(alias_tokens) <= len(place_tokens) and place_tokens[-len(alias_tokens) :] == alias_tokens:
        prefix = place_tokens[: len(place_tokens) - len(alias_tokens)]
        if prefix and all(token in _LEADING_LOCATION_TOKENS for token in prefix):
            return 0.90

    compact_place = place_candidate.replace(" ", "")
    compact_alias = alias_norm.replace(" ", "")
    if compact_place == compact_alias:
        return 0.97
    if compact_place.startswith(compact_alias):
        return 0.87

    if len(alias_tokens) <= 2 and alias_norm in _CHAIN_ABBREVIATIONS.values():
        if compact_place == compact_alias:
            return 0.96

    return 0.0


def _match_chain_entry(
    *,
    entry: Dict[str, Any],
    place_candidates: List[str],
    resolved_country: str,
) -> Dict[str, Any]:
    entry_country = _normalize_country_code(entry.get("country_code")) or "GLOBAL"
    country_bonus = 0.03 if entry_country == resolved_country else (-0.04 if entry_country != "GLOBAL" else 0.0)

    best_alias = ""
    best_candidate = ""
    best_score = 0.0
    for alias in _entry_aliases(entry):
        for candidate in place_candidates:
            score = _alias_match_score(candidate, alias)
            if score <= 0:
                continue
            score += country_bonus
            if score > best_score:
                best_score = score
                best_alias = alias
                best_candidate = candidate

    return {
        "score": best_score,
        "matched_alias": best_alias,
        "matched_candidate": best_candidate,
        "entry_country": entry_country,
    }


def _menu_items_for_entry(entry: Dict[str, Any], max_items: int = 12) -> List[Dict[str, Any]]:
    items = entry.get("items") if isinstance(entry.get("items"), list) else []
    out: List[Dict[str, Any]] = []
    official_url = str(entry.get("official_menu_source_url") or "").strip()

    for row in items:
        if not isinstance(row, dict):
            continue
        item_name = _normalize_space(row.get("item_name"))
        if not item_name:
            continue

        confidence = float(row.get("menu_item_confidence") or row.get("menu_confidence") or 0.86)
        confidence = max(0.45, min(0.98, confidence))

        out.append(
            {
                "item_name": item_name,
                "category": _normalize_space(row.get("category")),
                "estimated_calories": int(float(row.get("estimated_calories") or 0) or 0),
                "estimated_protein_g": int(float(row.get("estimated_protein_g") or 0) or 0),
                "estimated_carbs_g": int(float(row.get("estimated_carbs_g") or 0) or 0),
                "estimated_fat_g": int(float(row.get("estimated_fat_g") or 0) or 0),
                "estimated_satiety": str(row.get("estimated_satiety") or "").strip().lower(),
                "confidence": round(confidence, 2),
                "menu_confidence": round(confidence, 2),
                "source": _CHAIN_MENU_SOURCE,
                "menu_source": _CHAIN_MENU_SOURCE,
                "menu_item_source": "chain_registry",
                "menu_item_confidence": round(confidence, 2),
                "source_url": str(row.get("source_url") or official_url),
                "extraction_method": _CHAIN_EXTRACTION_METHOD,
                "parse_method": _CHAIN_PARSE_METHOD,
                "parsed_via": _CHAIN_PARSED_VIA,
                "raw_text_snippet": _normalize_space(row.get("raw_text_snippet") or item_name)[:180],
                "chain_id": str(entry.get("chain_id") or "").strip(),
                "chain_key": str(entry.get("chain_key") or "").strip(),
                "chain_name": str(entry.get("chain_name") or "").strip(),
                "canonical_name": str(entry.get("chain_name") or "").strip(),
                "chain_name_resolved": str(entry.get("chain_name") or "").strip(),
                "country_code": str(entry.get("country_code") or "").strip().upper(),
                "source_type": str(entry.get("source_type") or "official_website_menu").strip(),
                "menu_last_updated": str(entry.get("menu_last_updated") or "").strip(),
                "official_menu_source_url": official_url,
            }
        )
        if len(out) >= max(1, int(max_items or 12)):
            break
    return out


def _select_entry_by_identity(
    chains: List[Dict[str, Any]],
    *,
    identity: Dict[str, Any],
    resolved_country: str,
) -> Dict[str, Any] | None:
    chain_id = str(identity.get("chain_id") or "").strip()
    if chain_id:
        for row in chains:
            if str((row or {}).get("chain_id") or "").strip() == chain_id:
                return row

    chain_key = str(identity.get("chain_key") or identity.get("brand_family") or "").strip().lower()
    if not chain_key:
        return None

    exact_country: List[Dict[str, Any]] = []
    global_rows: List[Dict[str, Any]] = []
    for row in chains:
        if str((row or {}).get("chain_key") or "").strip().lower() != chain_key:
            continue
        row_country = _normalize_country_code((row or {}).get("country_code")) or "GLOBAL"
        if row_country == resolved_country:
            exact_country.append(row)
        elif row_country == "GLOBAL":
            global_rows.append(row)

    if exact_country:
        return exact_country[0]
    if global_rows:
        return global_rows[0]
    return None


def resolve_chain_menu_for_place(
    place: Dict[str, Any] | None,
    *,
    country_code: str | None = None,
    max_items: int = 12,
) -> Dict[str, Any]:
    if not _env_bool("ENABLE_CHAIN_MENU_COVERAGE", default=True):
        return {}

    payload = place if isinstance(place, dict) else {}
    place_name = str(payload.get("name") or "").strip()
    place_candidates = _place_name_candidates(place_name)
    if not place_candidates:
        return {}

    resolved_country = _normalize_country_code(country_code) or _infer_country_code(payload) or DEFAULT_COUNTRY_CODE
    chains = list_chain_entries(country_code=resolved_country, include_global=True)

    best_entry: Dict[str, Any] | None = None
    identity = resolve_chain_identity(place_name=place_name, country_code=resolved_country, place=payload)
    best_alias = ""
    best_candidate = ""
    best_entry_country = ""
    best_score = 0.0
    if bool(identity.get("matched")):
        selected = _select_entry_by_identity(
            chains,
            identity=identity,
            resolved_country=resolved_country,
        )
        if selected:
            best_entry = selected
            best_alias = str(identity.get("matched_alias") or "")
            best_candidate = str(identity.get("matched_place_name") or "")
            best_score = float(identity.get("match_confidence") or 0.0)
            best_entry_country = _normalize_country_code(best_entry.get("country_code")) or "GLOBAL"

    if not best_entry:
        for entry in chains:
            candidate = _match_chain_entry(
                entry=entry,
                place_candidates=place_candidates,
                resolved_country=resolved_country,
            )
            score = float(candidate.get("score") or 0.0)
            if score > best_score:
                best_score = score
                best_entry = entry
                best_alias = str(candidate.get("matched_alias") or "")
                best_candidate = str(candidate.get("matched_candidate") or "")
                best_entry_country = str(candidate.get("entry_country") or "")

    if not best_entry or best_score < 0.78:
        return {}

    # Prefer ingested chain items over registry templates (offline ingestion pipeline)
    chain_key = str(best_entry.get("chain_key") or "").strip().lower()
    items: List[Dict[str, Any]] = []
    source_used = "chain_registry_template"
    if get_chain_items_for_registry:
        ingested = get_chain_items_for_registry(
            chain_key, market_tag=resolved_country, max_items=max_items, chain_entry=best_entry,
        )
        if ingested:
            items = ingested
            source_used = "ingested_chain_item"
    if not items:
        items = _menu_items_for_entry(best_entry, max_items=max_items)
    if not items:
        return {}

    avg_conf = sum(float(row.get("menu_confidence") or 0.0) for row in items) / max(1, len(items))
    official_url = str(best_entry.get("official_menu_source_url") or "").strip()
    if source_used == "chain_registry_template":
        source_used = "country_chain_registry" if best_entry_country == resolved_country else "global_chain_registry"
    for row in items:
        if not isinstance(row, dict):
            continue
        row["matched_alias"] = best_alias
        row["chain_source_used"] = source_used
        row["canonical_name"] = str(identity.get("canonical_name") or best_entry.get("chain_name") or "")
        row["chain_name_resolved"] = str(identity.get("canonical_name") or best_entry.get("chain_name") or "")

    return {
        "chain_match": True,
        "chain_match_confidence": round(max(0.2, min(0.99, best_score)), 2),
        "chain_id": str(best_entry.get("chain_id") or "").strip(),
        "chain_key": str(best_entry.get("chain_key") or "").strip(),
        "chain_name": str(best_entry.get("chain_name") or "").strip(),
        "canonical_name": str(identity.get("canonical_name") or best_entry.get("chain_name") or "").strip(),
        "chain_name_resolved": str(identity.get("canonical_name") or best_entry.get("chain_name") or "").strip(),
        "country_code": str(best_entry.get("country_code") or resolved_country).strip().upper(),
        "matched_alias": best_alias,
        "matched_place_name": best_candidate,
        "chain_source_used": source_used,
        "chain_match_detail": {
            "matched": True,
            "chain_id": str(best_entry.get("chain_id") or "").strip(),
            "chain_name": str(identity.get("canonical_name") or best_entry.get("chain_name") or "").strip(),
            "match_confidence": round(max(0.2, min(0.99, best_score)), 2),
            "matched_alias": best_alias,
            "country_code": str(best_entry.get("country_code") or resolved_country).strip().upper(),
            "chain_source_used": source_used,
            "chain_key": str(identity.get("chain_key") or best_entry.get("chain_key") or "").strip(),
            "brand_family": str(identity.get("brand_family") or ""),
        },
        "source_type": str(best_entry.get("source_type") or "official_website_menu").strip(),
        "menu_last_updated": str(best_entry.get("menu_last_updated") or "").strip(),
        "official_menu_source_url": official_url,
        "menu_items": items,
        "menu_source": "chain_menu_ingestion" if source_used == "ingested_chain_item" else _CHAIN_MENU_SOURCE,
        "menu_confidence": round(max(0.45, min(0.98, avg_conf)), 2),
        "extraction_method": _CHAIN_EXTRACTION_METHOD,
        "parse_method": _CHAIN_PARSE_METHOD,
        "source_url": official_url,
        "chain_registry_version": CHAIN_MENU_REGISTRY_VERSION,
    }
