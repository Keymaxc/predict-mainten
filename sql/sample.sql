

insert into machines (machine_name, machine_type, machine_model, production_line, install_date) values
    ('CNC Lathe 01',  'CNC Lathe', 'model2', 'Line A', '2021-03-15'),
    ('Press 02',      'Press',     'model3', 'Line A', '2020-08-01'),
    ('Conveyor 03',   'Conveyor',  'model1', 'Line B', '2022-01-10');


insert into sensor_readings (machine_id, reading_time, voltage, rotation_rpm, pressure, vibration, temperature)
select machine_id, ts, v, r, p, vib, t
from machines
cross join (values
    ('2025-03-01 08:00:00+07'::timestamptz, 170.2, 450.1, 100.5, 40.2, 72.4),
    ('2025-03-01 09:00:00+07'::timestamptz, 169.8, 449.7, 101.0, 40.9, 73.1),
    ('2025-03-01 10:00:00+07'::timestamptz, 171.5, 452.3,  99.8, 46.5, 79.8)
) as s(ts, v, r, p, vib, t)
where machine_name = 'CNC Lathe 01';

insert into error_logs (machine_id, error_time, error_code, error_description, severity)
select machine_id, '2025-03-01 10:15:00+07', 'E101', 'Getaran melebihi batas normal', 'medium'
from machines where machine_name = 'CNC Lathe 01';

insert into maintenance_logs (machine_id, maintenance_date, component, maintenance_type, cost_idr, downtime_hours)
select machine_id, '2025-02-20 07:00:00+07', 'bearing', 'preventive', 1200000, 3.0
from machines where machine_name = 'CNC Lathe 01';

insert into failures (machine_id, failure_time, component, failure_type, severity, downtime_hours)
select machine_id, '2025-03-01 14:30:00+07', 'bearing', 'bearing wear', 'high', 8.5
from machines where machine_name = 'CNC Lathe 01';


select 'machines'         as tabel, count(*) as jumlah_baris from machines
union all select 'sensor_readings',  count(*) from sensor_readings
union all select 'maintenance_logs', count(*) from maintenance_logs
union all select 'failures',         count(*) from failures
union all select 'error_logs',       count(*) from error_logs;


update machines
set    status = 'maintenance'
where  machine_name = 'Press 02';


update sensor_readings
set    temperature = 73.0
where  machine_id = (select machine_id from machines where machine_name = 'CNC Lathe 01')
  and  reading_time = '2025-03-01 09:00:00+07';


select  m.machine_name,
        m.production_line,
        count(f.failure_id)                  as jumlah_kerusakan,
        coalesce(sum(f.downtime_hours), 0)   as total_downtime_jam
from    machines m
left join failures f on f.machine_id = m.machine_id
group by m.machine_name, m.production_line
order by jumlah_kerusakan desc;


select  m.machine_name,
        f.failure_time,
        round(avg(s.vibration), 2)    as rata_getaran_24j,
        round(avg(s.temperature), 2)  as rata_suhu_24j
from    failures f
join    machines m         on m.machine_id = f.machine_id
join    sensor_readings s  on s.machine_id = f.machine_id
                          and s.reading_time >= f.failure_time - interval '24 hours'
                          and s.reading_time <  f.failure_time
group by m.machine_name, f.failure_time;
