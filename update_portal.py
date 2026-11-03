import requests
import json
import re
import time
from urllib.parse import quote

# Mekanisme Penembus Error 503 (Retry System)
def safe_request(url, headers, timeout=15, retries=3, delay=3):
    for i in range(retries):
        try:
            res = requests.get(url, headers=headers, timeout=timeout)
            if res.status_code == 200:
                return res
            elif res.status_code == 503:
                print(f"    [!] Server Error 503 (Sibuk). Mencoba kembali dalam {delay} detik... ({i+1}/{retries})")
                time.sleep(delay)
        except Exception:
            time.sleep(delay)
    return None

def main():
    print("Sedang mengambil data dari portal...")
    
    # ========================================================
    # 1. ATUR KREDENSIAL PORTAL ANDA DI SINI
    # ========================================================
    portal_url = "http://nxtbox.uk"  # URL portal asli Anda
    mac_address = "00:1A:79:D4:70:31"                  # MAC address Anda
    
    # Mendapatkan domain dasar tanpa subdirektori /c/
    if '/c/' in portal_url:
        base_url = portal_url.split('/c/')[0].rstrip('/')
    else:
        base_url = portal_url.rstrip('/')
        
    user_agent = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stalker/"
    headers = {
        "User-Agent": user_agent,
        "Cookie": f"mac={mac_address}"
    }

    try:
        # ========================================================
        # 2. PROSES HANDSHAKE & AUTENTIKASI TOKEN
        # ========================================================
        handshake_url = f"{base_url}/server/load.php?type=stb&action=handshake"
        req_handshake = safe_request(handshake_url, headers, timeout=15)
        
        token = ""
        if req_handshake and req_handshake.status_code == 200:
            try:
                res_json = req_handshake.json()
                token = res_json.get("js", {}).get("token", "")
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    print("-> Autentikasi Handshake Berhasil!")
            except:
                pass

        # ========================================================
        # 3. MENGAMBIL DAFTAR KATEGORI
        # ========================================================
        category_map = {}
        cat_actions = ["get_genres", "get_categories"]
        cat_loaded = False
        
        for action in cat_actions:
            if cat_loaded:
                break
            cat_url = f"{base_url}/server/load.php?type=itv&action={action}"
            try:
                cat_response = safe_request(cat_url, headers, timeout=15)
                if cat_response and cat_response.status_code == 200:
                    cat_data = cat_response.json()
                    cat_list = cat_data.get("js", [])
                    
                    if isinstance(cat_list, dict) and "data" in cat_list:
                        cat_list = cat_list.get("data", [])
                        
                    if isinstance(cat_list, list) and len(cat_list) > 0:
                        for cat in cat_list:
                            cat_id = str(cat.get("id", cat.get("number", "")))
                            cat_name = cat.get("title", cat.get("name", "")).strip()
                            if cat_id and cat_name:
                                category_map[cat_id] = cat_name
                        print(f"Berhasil memuat {len(category_map)} kategori via '{action}'.")
                        cat_loaded = True
            except:
                pass

        # ========================================================
        # 4. REQUEST SELURUH DAFTAR CHANNEL LIVE
        # ========================================================
        channel_url = f"{base_url}/server/load.php?type=itv&action=get_all_channels"
        response = safe_request(channel_url, headers, timeout=18)
        
        if not response or response.status_code != 200:
            print(f"Gagal memuat daftar channel.")
            return
            
        data = response.json()
        channels = data.get("js", {}).get("data", [])
        if not channels:
            channels = data.get("js", []) if isinstance(data.get("js"), list) else []

        if not channels:
            print("Tidak ada channel yang ditemukan dari respons portal.")
            return

        # ========================================================
        # 5. BANGUN PLAYLIST M3U DENGAN COCOK FOLDER KATEGORI & LOGO
        # ========================================================
        m3u_content = "#EXTM3U\n"
        count = 0
        
        for ch in channels:
            if not isinstance(ch, dict):
                continue
                
            name = ch.get("name", "Unknown Channel").strip()
            cmd = ch.get("cmd", "")
            ch_id = str(ch.get("id", "")).strip()
            
            # A. FILTER ELIMINASI KONTEN VOD / MOVIE
            if str(ch.get('is_vodi', '0')) == '1':
                continue
            if any(x in str(cmd).lower() for x in ['kinopoisk:', 'vclub:', 'pvr:', 'movie:', 'vclub_info:']):
                continue
            
            # Pencocokan Kategori
            ch_cat_id = ""
            for key in ["tv_genre_id", "tvg_id", "category_id", "ch_id"]:
                if key in ch and ch.get(key):
                    ch_cat_id = str(ch.get(key))
                    break
            
            group_title = category_map.get(ch_cat_id, ch.get('tv_genre_name', '').strip())
            
            # Penyelamatan cadangan kategori jika data grup kosong/Lainnya
            if not group_title or group_title == "Lainnya":
                # PERBAIKAN: Menggunakan pengondisian string aman (bukan regex pada nama channel mentah)
                # Mencari kode seperti (TR), [TR], dll. di depan nama
                clean_name_for_match = re.sub(r'[\(\)\[\]]', ' ', name).split()
                if clean_name_for_match and len(clean_name_for_match[0]) >= 2 and len(clean_name_for_match[0]) <= 4:
                    group_title = f"{clean_name_for_match[0].upper()} - Live TV"
                else:
                    group_title = "Live TV General"
                    
            if any(keyword in group_title.lower() for keyword in ['vod', 'movie', 'cinema', 'film', 'series']):
                continue

            # B. STRUKTUR UTAMA RESOLUSI LINK STREAM (ANTI-LOCALHOST)
            clean_cmd = str(cmd).replace('\\', '').strip()
            stream_id = clean_cmd.split('/')[-1].replace('"', '').replace("'", "").replace('_', '').strip()
            
            if not stream_id or len(stream_id) > 10 or not stream_id.isdigit():
                stream_id = ch_id
            
            # Memaksa pembuatan tautan sesuai target spesifik nxtbox Anda
            stream_url = f"{base_url}/play/live.php?mac={mac_address}&stream={stream_id}&extension=ts"

            # C. MEMPROSES LOGO SALURAN
            logo_file = ch.get("logo", ch.get("tvg_logo", ch.get("icon", "")))
            logo_url = ""
            
            if logo_file:
                logo_str = str(logo_file).strip()
                if logo_str.startswith("http"):
                    logo_url = logo_str
                else:
                    logo_file_clean = logo_str.lstrip('/')
                    if not any(logo_file_clean.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif']):
                        logo_file_clean += '.png'
                    logo_url = f"{base_url}/misc/logos/320/{logo_file_clean}"
            else:
                encoded_name = quote(name)
                logo_url = f"https://ui-avatars.com{encoded_name}&background=random&color=fff&size=256&font-size=0.35"

            safe_name = name.replace('"', "'")
            safe_group = group_title.replace('"', "'")

            # Tulis metadata ke baris M3U
            m3u_content += f'#EXTINF:-1 tvg-id="{ch_id}" tvg-name="{safe_name}" tvg-logo="{logo_url}" group-title="{safe_group}",{name}\n'
            m3u_content += f'#EXTVLCOPT:http-user-agent={user_agent}\n'
            m3u_content += f'#EXTVLCOPT:http-cookie=mac={mac_address}\n'
            m3u_content += f'{stream_url}\n'
            count += 1

        # ========================================================
        # 6. SIMPAN OUTPUT KE FILE PLAYLIST.M3U
        # ========================================================
        with open("playlist.m3u", "w", encoding="utf-8") as file:
            file.write(m3u_content)

        print(f"Proses Berhasil! Berhasil mengunci {count} saluran Live TV ke file 'playlist.m3u'.")

    except Exception as e:
        print(f"Terjadi kegagalan pemrosesan data: {e}")

if __name__ == "__main__":
    main()
