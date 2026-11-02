import requests
import json
import re
from urllib.parse import quote

def main():
    print("Sedang mengambil data dari portal...")
    
    # ========================================================
    # 1. ATUR KREDENSIAL PORTAL ANDA DI SINI
    # ========================================================
    portal_url = "http://nxtbox.uk/c/"  # Ganti dengan URL portal asli Anda
    mac_address = "00:1A:79:D4:70:31"                  # Ganti dengan MAC address Anda
    
    portal_url = portal_url.rstrip('/')
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stalker/",
        "Cookie": f"mac={mac_address}"
    }

    try:
        # ========================================================
        # 2. PROSES HANDSHAKE & AUTENTIKASI TOKEN
        # ========================================================
        handshake_url = f"{portal_url}/server/load.php?type=stb&action=handshake"
        req_handshake = requests.get(handshake_url, headers=headers, timeout=15)
        
        token = ""
        if req_handshake.status_code == 200:
            try:
                res_json = req_handshake.json()
                token = res_json.get("js", {}).get("token", "")
                if token:
                    headers["Authorization"] = f"Bearer {token}"
            except:
                pass

        # ========================================================
        # 3. MENGAMBIL DAFTAR KATEGORI (MENDUKUNG MULTI-ACTION: get_genres & get_categories)
        # ========================================================
        category_map = {}
        
        # Coba cara pertama: Menggunakan get_genres (Standar Stalker IPTV)
        cat_actions = ["get_genres", "get_categories"]
        cat_loaded = False
        
        for action in cat_actions:
            if cat_loaded:
                break
            cat_url = f"{portal_url}/server/load.php?type=itv&action={action}"
            try:
                cat_response = requests.get(cat_url, headers=headers, timeout=15)
                if cat_response.status_code == 200:
                    cat_data = cat_response.json()
                    cat_list = cat_data.get("js", [])
                    
                    # Jika response dibungkus data objek lagi
                    if isinstance(cat_list, dict) and "data" in cat_list:
                        cat_list = cat_list.get("data", [])
                        
                    if isinstance(cat_list, list) and len(cat_list) > 0:
                        for cat in cat_list:
                            cat_id = str(cat.get("id", cat.get("number", "")))
                            # Mengambil nama folder dari key 'title' atau 'name'
                            cat_name = cat.get("title", cat.get("name", "")).strip()
                            if cat_id and cat_name:
                                category_map[cat_id] = cat_name
                        print(f"Berhasil memuat {len(category_map)} kategori via '{action}'.")
                        cat_loaded = True
            except Exception as e:
                print(f"Gagal memuat via {action}, mencoba fallback berikutnya...")

        # ========================================================
        # 4. REQUEST SELURUH DAFTAR CHANNEL LIVE
        # ========================================================
        channel_url = f"{portal_url}/server/load.php?type=itv&action=get_all_channels"
        response = requests.get(channel_url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"Gagal memuat daftar channel. Status kode: {response.status_code}")
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
        
        for ch in channels:
            name = ch.get("name", "Unknown Channel").strip()
            ch_id = ch.get("id", "")
            
            # --- DETEKSI KUNCI ID KATEGORI PADA DATA CHANNEL ---
            # Menguji semua kemungkinan variabel pencocokan kategori di database Stalker
            ch_cat_id = ""
            for key in ["tv_genre_id", "tvg_id", "category_id", "ch_id"]:
                if key in ch and ch.get(key):
                    ch_cat_id = str(ch.get(key))
                    break
            
            # Tentukan nama folder, jika ID cocok, ambil dari map. Jika tidak, gunakan nama asal
            group_title = category_map.get(ch_cat_id, "Lainnya")
            
            # Memproses Link Streaming
            cmd = ch.get("cmd", "")
            stream_url = ""
            if "http" in cmd:
                match = re.search(r'(https?://[^\s"\']+)', cmd)
                stream_url = match.group(1) if match else cmd
            else:
                stream_url = f"{portal_url}/itv/{ch_id}"

            # Memproses Logo dari data Mac Portal dengan format nama file
            logo_file = ch.get("logo", ch.get("tvg_logo", ch.get("icon", "")))
            logo_url = ""
            
            if logo_file:
                if logo_file.startswith("http"):
                    logo_url = logo_file
                else:
                    logo_file_clean = logo_file.lstrip('/')
                    logo_url = f"{portal_url}/misc/logos/{logo_file_clean}"
            else:
                encoded_name = quote(name)
                logo_url = f"https://ui-avatars.com{encoded_name}&background=random&color=fff&size=256&font-size=0.35"

            # Tulis metadata ke baris M3U
            m3u_content += f'#EXTINF:-1 tvg-id="{ch_id}" tvg-name="{name}" tvg-logo="{logo_url}" group-title="{group_title}",{name}\n'
            
            # Tambahkan konfigurasi pembacaan MAC & User agent untuk OTT Navigator
            m3u_content += f'#EXTVLCOPT:http-user-agent={headers["User-Agent"]}\n'
            m3u_content += f'#EXTVLCOPT:http-cookie=mac={mac_address}\n'
            m3u_content += f'{stream_url}\n'

        # ========================================================
        # 6. SIMPAN OUTPUT KE FILE PLAYLIST.M3U
        # ========================================================
        with open("playlist.m3u", "w", encoding="utf-8") as file:
            file.write(m3u_content)

        print("Proses Berhasil! Folder kategori dan logo telah dipetakan ulang dengan benar.")

    except Exception as e:
        print(f"Terjadi kegagalan pemrosesan data: {e}")

if __name__ == "__main__":
    main()
