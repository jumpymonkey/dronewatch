-- DroneWatch Database Seed Data

INSERT INTO drone_streams (stream_id, drone_name, rtsp_url, status, is_simulation, source_file)
VALUES 
    ('9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d', 'Perimeter Drone Alpha', 'rtsp://localhost:8554/sim/dji_0104', 'ACTIVE', true, 'DJI_0104.MP4'),
    ('c3a1f9e2-8b4a-4f11-9a7c-123456789abc', 'North Fence Patrol', 'rtsp://localhost:8554/sim/s1001976', 'ACTIVE', true, 'S1001976.MP4'),
    ('f7d2e4c1-5a6b-7c8d-9e0f-112233445566', 'East Yard Drone', 'rtsp://localhost:8554/sim/dji_0108', 'INACTIVE', true, 'DJI_0108.MP4')
ON CONFLICT (rtsp_url) DO UPDATE 
SET status = EXCLUDED.status, updated_at = CURRENT_TIMESTAMP;
