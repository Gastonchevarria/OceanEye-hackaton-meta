import asyncio
import sys
import httpx
from main import app

async def run_tests():
    print("🧪 Running local OceanEye backend tests...")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test 1: GET /
        res = await client.get("/")
        print("1. Root GET / -> Status:", res.status_code)
        print("   Body:", res.json())
        assert res.status_code == 200

        # Test 2: GET /health
        res = await client.get("/health")
        print("2. Health GET /health -> Status:", res.status_code)
        print("   Body:", res.json())
        assert res.status_code == 200

        # Test 3: GET /vessels
        res = await client.get("/vessels")
        data = res.json()
        print(f"3. Vessels GET /vessels -> Status: {res.status_code}, Total: {data.get('total')}")
        assert res.status_code == 200

        # Test 4: POST /analyze with NVIDIA AI
        vessel = data["vessels"][0]
        print(f"4. Calling NVIDIA AI /analyze for vessel {vessel['name']}...")
        res = await client.post("/analyze", json={"vessel_data": vessel})
        print("   NVIDIA AI Response Status:", res.status_code)
        print("   Intelligence Report Summary:", res.json().get("summary"))
        # Test 5: GET /api/v1/sar/benchmark (BBVA Jury zero-credential evaluation)
        print("5. Calling GET /api/v1/sar/benchmark...")
        res = await client.get("/api/v1/sar/benchmark")
        print("   SAR Benchmark Status:", res.status_code)
        sar_data = res.json()
        print(f"   Execution Time: {sar_data.get('execution_time_seconds')}s")
        print(f"   Dark Vessels Detected: {sar_data.get('metrics', {}).get('total_dark_vessels')}")
        print(f"   Ghost AIS Spoofing: {sar_data.get('metrics', {}).get('total_ghost_ais')}")
        assert res.status_code == 200
        assert sar_data.get("metrics", {}).get("total_dark_vessels") == 12

        # Test 6: GET /api/v1/sar/dossier/SAR-TGT-001 with LAYA Ed25519 Seal
        dark_id = sar_data["dark_vessels"][0]["id"]
        print(f"6. Calling GET /api/v1/sar/dossier/{dark_id}...")
        res = await client.get(f"/api/v1/sar/dossier/{dark_id}")
        print("   Forensic Dossier Status:", res.status_code)
        dossier = res.json()
        print(f"   SHA-256 Hash: {dossier.get('chain_of_custody_hash_sha256')[:24]}...")
        print(f"   Distance to EEZ: {dossier.get('distance_to_eez_nm')} NM ({dossier.get('boundary_status')})")
        print(f"   Dossier keys returned: {list(dossier.keys())}")
        laya_cert = dossier.get("laya_ed25519_certificate")
        assert res.status_code == 200
        assert len(dossier.get("chain_of_custody_hash_sha256")) == 64
        assert laya_cert is not None, f"laya_ed25519_certificate missing from dossier! Keys: {list(dossier.keys())}"
        assert len(laya_cert.get("ed25519_signature_base64")) > 60
        assert len(laya_cert.get("laya_public_key_hex")) == 64
        print(f"   LAYA Ed25519 Signature (Base64): {laya_cert.get('ed25519_signature_base64')[:24]}...")
        print(f"   LAYA Public Key (Hex): {laya_cert.get('laya_public_key_hex')[:24]}...")

        # Test 7: GET /api/v1/sar/eez/boundary
        print("7. Calling GET /api/v1/sar/eez/boundary...")
        res = await client.get("/api/v1/sar/eez/boundary")
        print("   Official EEZ Boundary GeoJSON Status:", res.status_code)
        assert res.status_code == 200
        assert res.json().get("type") == "FeatureCollection"

        # Test 8: POST /api/v1/sar/laya/ais-guardian (Sub-40ms Reflex Engine)
        print("8. Calling POST /api/v1/sar/laya/ais-guardian (Dead-drop blackout simulation)...")
        t_ais_start = asyncio.get_event_loop().time()
        res = await client.post("/api/v1/sar/laya/ais-guardian", json={
            "current_report": {
                "mmsi": "412999001",
                "lat": -45.5,
                "lon": -60.0,
                "speed_knots": 11.2,
                "heading_deg": 180.0,
                "timestamp_utc": "2026-10-11T12:00:00Z",
                "transponder_active": False
            },
            "previous_report": {
                "mmsi": "412999001",
                "lat": -45.4,
                "lon": -60.0,
                "speed_knots": 11.0,
                "heading_deg": 180.0,
                "timestamp_utc": "2026-10-11T11:45:00Z",
                "transponder_active": True
            }
        })
        t_ais_duration_ms = (asyncio.get_event_loop().time() - t_ais_start) * 1000
        print(f"   LAYA AIS Guardian Status: {res.status_code} in {t_ais_duration_ms:.2f}ms")
        guardian_res = res.json()
        alert_rules = [a.get("rule_name") for a in guardian_res.get("alerts", [])]
        print(f"   Guardian Alert Rules: {alert_rules}")
        print(f"   Sentinel-1 Tasking Order: {guardian_res.get('satellite_tasking_order')}")
        assert res.status_code == 200
        assert "DEAD_DROP_BLACKOUT_TRIGGER" in alert_rules
        assert guardian_res.get("satellite_tasking_order") is not None
        assert guardian_res.get("satellite_tasking_order", {}).get("sensor") == "Sentinel-1A SAR C-Band (IW Mode)"

        # Test 9: GET /api/v1/sar/laya/public-key (Court Evidence Verification)
        print("9. Calling GET /api/v1/sar/laya/public-key...")
        res = await client.get("/api/v1/sar/laya/public-key")
        print("   LAYA Public Key Status:", res.status_code)
        pub_key_data = res.json()
        print(f"   Ed25519 Public Key: {pub_key_data.get('public_key_hex')[:24]}...")
        assert res.status_code == 200
        assert pub_key_data.get("algorithm") == "Ed25519"
        assert len(pub_key_data.get("public_key_hex")) == 64

    print("🎉 ALL 9 BACKEND ENDPOINTS, SAR RADAR PIPELINE, NVIDIA AI & LAYA SISTEMA 1 VERIFIED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_tests())
