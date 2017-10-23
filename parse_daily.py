#!/usr/bin/env python3

import json, os, sqlite3
from collections import Counter

#sqlite has no real equivalent to "TRUNCATE TABLE x". "DELETE FROM x" is recommended but it's slow.
#It turns out that dropping the table is also slow. It follows that the quickest way to remove all
#rows is to delete the DB file itself
try:
    os.remove('schedule.db')
except FileNotFoundError:
    pass
conn = sqlite3.connect('schedule.db')
c = conn.cursor()
c.execute("""CREATE TABLE schedules(
    uid CHAR(6),
    stp CHAR(1),
    valid_from DATE,
    valid_to DATE,
    running_days CHAR(7),
    atoc_code CHAR(2),
    status CHAR(1),
    cif_category CHAR(2),
    signalling_id CHAR(4),
    cif_power_type CHAR(3),
    cif_timing_load CHAR(7),
    cif_speed INTEGER,
    entry BLOB
);""")
c.execute("CREATE INDEX idx_uid ON schedules(uid);")

c.execute("""CREATE TABLE associations(
    uid CHAR(6),
    uid_assoc CHAR(6),
    stp CHAR(1),
    valid_from DATE,
    valid_to DATE,
    assoc_days CHAR(7),
    date_indicator CHAR(1),
    category CHAR(2),
    tiploc CHAR(7),
    suffix CHAR(1),
    suffix_assoc CHAR(1)
);""")
c.execute("CREATE INDEX idx_main_uid ON associations(uid);")
c.execute("CREATE INDEX idx_assoc_uid ON associations(uid_assoc);")

count = 0
with open("sched_daily.txt") as f:
    for line in f:
        jline = json.loads(line)
        if "JsonScheduleV1" in jline:
            count +=1
            if count%1000==0:
                print(count)
            segment = jline["JsonScheduleV1"]["schedule_segment"]
            sched = jline["JsonScheduleV1"]

            c.execute("INSERT INTO schedules VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                sched["CIF_train_uid"],
                sched["CIF_stp_indicator"],
                sched["schedule_start_date"],
                sched["schedule_end_date"],
                sched["schedule_days_runs"],
                sched.get("atoc_code", ''),
                sched["train_status"],
                segment.get("CIF_train_category", None),
                segment["signalling_id"],
                segment["CIF_power_type"],
                segment["CIF_timing_load"],
                segment["CIF_speed"],
                json.dumps(sched)
                ))
        elif "JsonAssociationV1" in jline:
            assoc = jline["JsonAssociationV1"]
            c.execute("INSERT INTO associations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                assoc["main_train_uid"], assoc["assoc_train_uid"],
                assoc["CIF_stp_indicator"],
                assoc["assoc_start_date"][:10], assoc["assoc_end_date"][:10],
                assoc["assoc_days"],
                assoc["date_indicator"],
                assoc["category"],
                assoc["location"],
                assoc["base_location_suffix"],
                assoc["assoc_location_suffix"]
                ))

conn.commit()
conn.close()
