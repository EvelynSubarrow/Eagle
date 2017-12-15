import json
from collections import OrderedDict

with open("images.json") as f:
    IMAGES = json.load(f)

#ATOC, power, speed, timing load, "train class" (reservation availability)
TOPS_INFERENCES = [
    (("VT", "EMU", "125", "390", None), ["390"], "Pendolino"),
    (("LO", "EMU", "075", "375", None), ["378"], "Capitalstar", IMAGES["lo378"]),
    (("LO", "EMU", "075", "313", None), ["378"], "Capitalstar", IMAGES["lo378"]),
    (("LO", "EMU", None , "315", None), ["315"]),
    (("LO", "EMU", None , "317", None), ["317"], None, IMAGES["xn317"]),
    (("XR", "EMU", None , "315", None), ["315"]),
    (("SR", "EMU", None , "0",   None), ["380"], "Desiro", IMAGES["sr380"]),
    (("LM", "EMU", None , "350", None), ["350"], "Desiro", IMAGES["lm350"]),
    (("LM", "EMU", None , "323", None), ["323"]),
    (("TP", "EMU", None , "350", None), ["350"], "Desiro", IMAGES["tp350"]),
    (("ME", "EMU", None , None , None), ["507", "508"], None, IMAGES["me507-508"]),
    (("SE", "EMU", None , "395", None), ["395"], "Javelin", IMAGES["se395"]),

    ((None, "EMU", None , "321", None), ["321"]), #LE
    ((None, "EMU", None , "357", None), ["357"]), #LE
    ((None, "EMU", None , "483", None), ["483"]), #IL
    ((None, "HST", None , None , None), ["43"], "High Speed Train"),   #HST means IC125 in practice. 225s are 'E'

    #SW EMUs can only be distinguished by seating classes, which is fine
    (("SW", "EMU", None , None,  "S"), ["455", "456", "458", "707"]),
    (("SW", "EMU", None , None,  "B"), ["444", "450", "458"]),
    #SW only operates 159s (by technicality of renumbering, but that's fine)
    (("SW", "DMU", None , "X", None),   ["159"], "South Western Turbo", IMAGES["xn159"]),

    #HX only properly indicates class for HXX(2/3)-HAF(4) 360/2 services
    (("HX", "EMU", None , "360", None), ["360"], "Desiro"),
    (("HX", "EMU", None ,  None, None), ["332"]),

    #NT doesn't operate any 143s, so exclude
    (("NT", "DMU", None , "A", None),   ["142", "144"], "Pacer"),

    #GW only operates class 143 pacers
    (("GW", "DMU", None , "A", None),   ["143"], "Pacer"),

    #EM operates only two "high speed" classes. 222 *should* be DEM but whatever
    (("EM", "DMU", "125", None, None),  ["222"], "Meridian", IMAGES["em222"]),

    #GR (VTEC)'s only 'E' locos *must* be IC225s
    (("GR", "E",   "125" , None, None), ["91"]),

    #Non-TOC-specific DMU ranges
    ((None, "DMU", None , "A", None),   ["142", "143", "144"], "Pacer"),
    ((None, "DMU", None , "E", None),   ["158", "168", "170", "175"]),
    ((None, "DMU", None , "N", None),   ["165"], "Network Turbo"),
    ((None, "DMU", None , "S", None),   ["150", "153", "155", "156"], "(Super) Sprinter"),
    ((None, "DMU", None , "T", None),   ["165", "166"]),
    ((None, "DMU", None , "V", None),   ["220", "221"], "(Super) Voyager"),
    ((None, "DMU", None , "X", None),   ["158", "159"], "Express Sprinter", IMAGES["xn159"]),
    ]

def infer(current):
    nonetype = OrderedDict(tops_inferred=None, tops_possible=[], tops_familiar=None, tops_image=None)
    if not current:
        return nonetype
    tuple = (current["atoc_code"], current["power_type"], current["speed"],
        current["timing_load"], current["seating_class"])
    for entry in TOPS_INFERENCES:
        key,classes,familiar,image = (entry + (None,None))[:4]
        if all([not y or x==y for x,y in zip(tuple, key)]):
            return OrderedDict(tops_inferred="/".join(classes), tops_possible=classes, tops_familiar=familiar, tops_image=image)
    return nonetype
