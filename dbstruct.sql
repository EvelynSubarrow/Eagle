CREATE TABLE schedules(
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
);
CREATE INDEX idx_uid ON schedules(uid);
