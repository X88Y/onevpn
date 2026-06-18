#!/usr/bin/env python3
"""One-shot downloader for support FAQ screenshots (VK CDN URLs)."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

BOT_DIR = Path(__file__).resolve().parents[1]
MANUAL_DIR = BOT_DIR / "assets" / "manual"

# filename -> full VK CDN URL (query string must be preserved)
SUPPORT_IMAGE_URLS: dict[str, str] = {
    "err_na_1.jpg": "https://sun9-55.userapi.com/s/v1/ig2/WtcKM_nMku5w2kWDl3CkUW_IcoRAbAsDKjWagwxvS-LhAWAXmnCHN5qWph7AARID3BTW52DwWL8xIKFEYrON905I.jpg?quality=95&as=32x37,48x56,72x84,108x125,160x186,240x279,360x418,480x557,540x627,640x743,720x836,1080x1254,1280x1487,1320x1533&from=bu&u=sgSGEmUL0Ulqe8mA1eXJx0YDdY7H6oGY_mT1UeqwgTM",
    "err_na_2.jpg": "https://sun9-19.userapi.com/s/v1/ig2/ZYVmQljC6SL7D5esrPUrg6GPJ1_5HjpeeUsaNDHzczMah06PH5wMURLqdVpLqLn3D22V5KDOMYGVoDoTRe3lSlps.jpg?quality=95&as=32x43,48x64,72x96,108x144,160x213,240x320,360x480,480x640,540x720,640x853,720x960,1080x1440,1280x1707,1440x1920,1920x2560&from=bu&u=H-wFCbull_2RV9G1n4G646NJhT4011YlABR3Jv-2JyU",
    "err_502_1.jpg": "https://sun9-77.userapi.com/s/v1/ig2/Gw3TTHnUqDfaECWCCDwsqkgNTrY9x8jK6Pbj5vJxLBod75MQkbnhjanPWUczOiFh-dcSdegIbegnQYwmhQjF3Qgy.jpg?quality=95&as=32x13,48x20,72x30,108x45,160x67,240x101,360x151,480x202,540x227,590x248&from=bu&u=na12Tc0hZ273U_TFJP1vKGbVQdyjWFpKr0d3_IdfmXs",
    "err_429_1.jpg": "https://sun9-80.userapi.com/s/v1/ig2/y778VFqUAdmHUaDHRKU-k_AL0N179QHDu7iMBJWmsbsiZsAihMiJ5wVNRdQgKc9w4yYueuKV_Klg_9Rei8LFaaEl.jpg?quality=95&as=32x8,48x12,72x18,108x26,160x39,240x59,360x88,480x117,540x132,589x144&from=bu&u=Ql5fhhszlh4Tzb7yW80-XRS9sMjlfgleAbbnFi8SXkM",
    "err_403_1.jpg": "https://sun9-42.userapi.com/s/v1/ig2/RXqo4ktoJ2rtsMSwl3l_tCSgoSPYL7oN2MrBp7KQi7RvPzhGZmGUtJyxlRbCJA-pY1rehd3RdGttMvubzmnzf5Xr.jpg?quality=95&as=32x12,48x19,72x28,108x42,160x62,240x94,360x140,480x187,540x210,640x249,720x281,1080x421,1178x459&from=bu&u=LnjFTqR2G65CbnV0j_zy6OieDgj0fk_MZIzFQJDCZ-k",
    "err_403_2.jpg": "https://sun9-85.userapi.com/s/v1/ig2/OaLwVg65IGrRhAKsyFRdk2xRaGquwpeclSqaD_fA3K7zZ8pHLaOh6Lkp0d-xZ1_AayxbkzwICs6D6otTL5BEziw2.jpg?quality=95&as=32x6,48x9,72x14,108x21,160x31,240x47,360x70,480x93,540x105,576x112&from=bu&u=GP5v5V5mP2Qm3RfFOCWQzI7-z5F3JCLKHddFjXohWDY",
    "err_tls_1.jpg": "https://sun9-29.userapi.com/s/v1/ig2/T4GUHCgC4C7bnO7Ei1tVN7DWYhWWiLMO7qpkBbOjE9H2_rAA0-NdOjCJMQ-Seyxpn0Ju5y0QDUuglW1EqkMqFLYE.jpg?quality=95&as=32x22,48x34,72x50,108x75,160x112,240x168,360x251,480x335,540x377,640x447,720x503&from=bu&u=jsg2-RstOxyFJ1ySdOHmsZJMkCDC0zMPejxY_dgcPAs",
    "err_geo_1.jpg": "https://sun9-60.userapi.com/s/v1/ig2/JZDqZ-p93hkRoUAqD8PGisGjClk6xvYCslrSoqej19FtZZSwnTBU5dWyrda11qIs7Hhes3_gZnQN9LW2CyBxU3Y5.jpg?quality=95&as=32x28,48x42,72x63,108x94,160x140,240x210,360x315,480x420,540x472,640x560,720x630,1080x945,1280x1120,1320x1155&from=bu&u=lej0UgdTRhUQ8OyfweUb6-xlLckpwTf7-KNOshbyq2Q",
    "err_geo_2.jpg": "https://sun9-30.userapi.com/s/v1/ig2/sU0uUns9rNJ95BBL05clK7hXwbcZJtiIoAazJwyZnOt7GHMfYIUINlvmdmiT1tAEnmsbSUz04_NaI3XjCAPFReWK.jpg?quality=95&as=32x7,48x10,72x15,108x22,160x33,240x49,360x74,480x98,540x110,640x131,720x147,1080x221,1280x262,1320x270&from=bu&u=Arenq1JWp-k5iIByIpVkzP6cdCEtYpiDiBjAM2L-5f0",
    "err_geo_3.jpg": "https://sun9-17.userapi.com/s/v1/ig2/x1q67d5kmi83Vd0avELo2wwN6qZ9GmtsAGbznvqdqXEs9Z1f1FF6y5eV-mPQsZpBAQ8kZGo5KPvEffGU8lZhO6Oi.jpg?quality=95&as=32x45,48x68,72x102,108x153,160x227,240x341,360x512,480x682,540x767,640x910,720x1023,1080x1535,1280x1819,1320x1876&from=bu&u=jXElv-AlVK7wGPmIHQUgtZ92-sLM0UFyyzKHhYazTGs",
    "err_telegram_1.jpg": "https://sun9-61.userapi.com/s/v1/ig2/W3k_vWob71HNXk7uEvuldadUwxQx5Q7SqU4oQGyVeGkpwtEXU6W8adX__93iZoALcNqYDwmj75LpyVyfPAXNOTrx.jpg?quality=95&as=32x16,48x24,72x36,108x54,160x80,240x121,360x181,480x241,540x271,640x321,720x362,1080x542,1280x643,1320x663&from=bu&u=J7iAJL2puASQpEPDLh068qlyz0Pe-42O5HqF4_x_xA8",
    "err_connect_1.jpg": "https://sun9-33.userapi.com/s/v1/ig2/jZBiTOd8sKpTZZTFNh9kdHwyXn2INhR9TLatuJaHly-AnpgXRDASfHUGfc7pyCJjvlQM3bJkaHvECnCi1Zau2eUk.jpg?quality=95&as=32x12,48x18,72x27,108x41,160x60,240x91,360x136,480x181,540x204,640x241,720x272,1080x407,1280x483,1320x498&from=bu&u=MTgIovyxI2kNTd0OIJ2KDTle9b3JKul73jGiN5Gyhkw",
    "err_connect_2.jpg": "https://sun9-58.userapi.com/s/v1/ig2/Z9KeeK6GQPRMi_yRM9RSjbKp73GhlFeXWOed3oiHvzoNX61PZsuJDc9pXNSUYTQu4AJxxfMPPBq6Na1gFZWMiYiY.jpg?quality=95&as=32x8,48x13,72x19,108x28,160x42,240x63,360x94,480x125,540x141,640x167,720x188,1080x282,1280x335,1320x345&from=bu&u=uweV7GQcTImurkYCJ49rZds8Db2Q563NooLe58dX7GQ",
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def download_all() -> int:
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    failed = 0

    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        for filename, url in SUPPORT_IMAGE_URLS.items():
            dest = MANUAL_DIR / filename
            print(f"Downloading {filename}...")
            try:
                response = client.get(url, headers={"User-Agent": USER_AGENT})
                if response.status_code != 200:
                    print(
                        f"  FAILED ({response.status_code}): {filename}\n"
                        "  Hint: re-fetch via VK API photos.getById if CDN token expired."
                    )
                    failed += 1
                    continue
                dest.write_bytes(response.content)
                print(f"  OK -> {dest} ({len(response.content)} bytes)")
            except Exception as exc:
                print(f"  ERROR: {filename}: {exc}")
                failed += 1

    return failed


if __name__ == "__main__":
    sys.exit(1 if download_all() else 0)
