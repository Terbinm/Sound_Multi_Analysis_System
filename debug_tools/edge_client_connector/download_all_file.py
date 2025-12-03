import requests, os, time, json, re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import RequestException, Timeout

SERVER_URL = 'http://163.18.22.51:88'
DOWNLOAD_DIR = "downloaded_recordings"
MANIFEST_PATH = os.path.join(DOWNLOAD_DIR, "download_manifest.json")

# 建立一個全域 Session，帶重試策略
_session = requests.Session()
_retries = Retry(
    total=3,                # 總重試次數（含 read/連線/狀態碼）
    connect=3,
    read=3,
    backoff_factor=1.0,     # 1, 2, 4 秒… 指數退避
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)
_session.mount("http://", HTTPAdapter(max_retries=_retries))
_session.mount("https://", HTTPAdapter(max_retries=_retries))

def _load_manifest():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"items": {}}  # { id: {filename, status, size, downloaded, path, url, updated_ts} }

def _save_manifest(m):
    tmp = MANIFEST_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    os.replace(tmp, MANIFEST_PATH)

def _tmp_name(filename, recording_id):
    # 將 id 放進暫存檔名
    safe_id = str(recording_id)
    return os.path.join(DOWNLOAD_DIR, f"{filename}.__id_{safe_id}.part")

def _meta_name(tmp_path):
    return tmp_path + ".meta.json"

def _legacy_tmp_name(filename):
    # 舊版你的寫法：filename.part
    return os.path.join(DOWNLOAD_DIR, filename + ".part")

def get_all_recordings():
    try:
        r = _session.get(f"{SERVER_URL}/recordings", timeout=(5, 10))
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"獲取錄音列表失敗：{e}")
        return []

def list_incomplete_parts():
    """
    掃描 DOWNLOAD_DIR，把所有 *.part 列表化，解析出 __id_XXX，
    回傳清單：[{"id": "123", "tmp": "...", "filename": "..."}]
    """
    results = []
    if not os.path.isdir(DOWNLOAD_DIR):
        return results
    pat = re.compile(r"^(?P<filename>.+)\.__id_(?P<id>[^.]+)\.part$")
    for name in os.listdir(DOWNLOAD_DIR):
        if not name.endswith(".part"):
            continue
        m = pat.match(name)
        if m:
            results.append({
                "id": m.group("id"),
                "tmp": os.path.join(DOWNLOAD_DIR, name),
                "filename": m.group("filename")
            })
        else:
            # 兼容舊格式：xxxx.part（無 id），標註為未知 id
            results.append({
                "id": None,
                "tmp": os.path.join(DOWNLOAD_DIR, name),
                "filename": name[:-5]  # 去掉 .part
            })
    return results

def _write_meta(meta_path, data):
    data["updated_ts"] = time.time()
    tmp = meta_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, meta_path)

def download_recording(
    recording,
    connect_timeout=5,
    read_timeout=8,         # 單次讀取逾時短一點，便於偵測卡住
    overall_timeout=60*20,  # 單檔上限時間
    stall_timeout=30,       # 兩次進度間隔不可超過
    max_stall_retries=5,    # 連續續傳最多 5 次
    chunk_size=64 * 1024    # 64 KB，增加進度回報頻率
):
    recording_id = str(recording["id"])
    filename = recording["filename"]

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    dst = os.path.join(DOWNLOAD_DIR, filename)
    tmp = _tmp_name(filename, recording_id)  # 新格式含 id
    meta_path = _meta_name(tmp)
    url = f"{SERVER_URL}/download/{recording_id}"

    print(f"開始下載：{filename} (id={recording_id})")

    # 兼容舊格式：若存在 legacy tmp，且新 tmp 不存在 → 改名成新格式（帶 id）
    legacy = _legacy_tmp_name(filename)
    if os.path.exists(legacy) and not os.path.exists(tmp):
        try:
            os.replace(legacy, tmp)
            print(f"  偵測到舊的暫存檔，已改名為新格式：{os.path.basename(tmp)}")
        except Exception as _:
            pass

    start_t = time.monotonic()
    last_progress_t = start_t
    bytes_written = 0
    expected_total = None

    if os.path.exists(tmp):
        bytes_written = os.path.getsize(tmp)

    stall_retries = 0

    def open_stream(resume_from):
        headers = {"Accept-Encoding": "identity"}
        if resume_from > 0:
            headers["Range"] = f"bytes={resume_from}-"
        resp = _session.get(
            url, stream=True, timeout=(connect_timeout, read_timeout), headers=headers
        )
        resp.raise_for_status()
        # 取得 Content-Length（若是 206 則為剩餘長度）
        cl = resp.headers.get("Content-Length")
        if cl is not None:
            try:
                return resp, int(cl)
            except ValueError:
                return resp, None
        return resp, None

    manifest = _load_manifest()
    manifest["items"].setdefault(recording_id, {
        "filename": filename, "status": "pending", "size": None,
        "downloaded": bytes_written, "path": dst, "url": url
    })
    manifest["items"][recording_id]["status"] = "in_progress"
    manifest["items"][recording_id]["downloaded"] = bytes_written
    _save_manifest(manifest)

    # 初始化/更新 meta 側車檔
    _write_meta(meta_path, {
        "id": recording_id,
        "filename": filename,
        "url": url,
        "expected_total": None,
        "bytes_written": bytes_written,
        "status": "in_progress"
    })

    try:
        # 先開檔（append 模式，續傳時直接接著寫）
        with open(tmp, "ab") as f:
            resp, this_len = open_stream(bytes_written)
            # 如果是第一次開，估一下總長
            if bytes_written == 0:
                expected_total = this_len
            else:
                # 續傳時 expected_total 只能用「已寫 + 剩餘」來估
                if this_len is not None:
                    expected_total = bytes_written + this_len

            # 記下預期大小
            if expected_total is not None:
                manifest["items"][recording_id]["size"] = expected_total
                _save_manifest(manifest)
                _write_meta(meta_path, {
                    "id": recording_id,
                    "filename": filename,
                    "url": url,
                    "expected_total": expected_total,
                    "bytes_written": bytes_written,
                    "status": "in_progress"
                })

            while True:
                # 整體時間限制
                if time.monotonic() - start_t > overall_timeout:
                    raise Timeout(f"超過整體下載時限 {overall_timeout}s")

                try:
                    progressed = False
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            bytes_written += len(chunk)
                            progressed = True
                            now = time.monotonic()
                            if now - last_progress_t >= 2:
                                if expected_total:
                                    pct = bytes_written * 100 / expected_total
                                    speed = bytes_written / (now - start_t + 1e-9)
                                    print(f"  進度：{pct:.1f}%  已收:{bytes_written}  速率:{speed/1024/1024:.2f} MB/s")
                                else:
                                    speed = bytes_written / (now - start_t + 1e-9)
                                    print(f"  已收:{bytes_written} bytes  速率:{speed/1024/1024:.2f} MB/s")
                                last_progress_t = now

                                # 週期性更新 manifest / meta
                                manifest["items"][recording_id]["downloaded"] = bytes_written
                                _save_manifest(manifest)
                                _write_meta(meta_path, {
                                    "id": recording_id,
                                    "filename": filename,
                                    "url": url,
                                    "expected_total": expected_total,
                                    "bytes_written": bytes_written,
                                    "status": "in_progress"
                                })

                            # 若有進度就重置 stall 計數
                            stall_retries = 0

                        # 無進度監測（例如伺服器在 chunk 邊界卡住）
                        if time.monotonic() - last_progress_t > stall_timeout:
                            raise Timeout(f"{stall_timeout}s 無進度，準備續傳")

                    # for 走完 → 代表伺服器關閉串流（下載可能完成）
                    break

                except (requests.exceptions.ReadTimeout, Timeout):
                    # 讀取逾時或長時間無進度：重新打開連線續傳
                    stall_retries += 1
                    if stall_retries > max_stall_retries:
                        raise Timeout(f"續傳已超過 {max_stall_retries} 次，放棄此檔")
                    print(f"  偵測到卡住，嘗試續傳第 {stall_retries}/{max_stall_retries} 次（已收 {bytes_written} bytes）")
                    try:
                        resp.close()
                    except Exception:
                        pass
                    # 重新開流，從目前位移續傳
                    resp, this_len = open_stream(bytes_written)
                    if expected_total is None and this_len is not None:
                        expected_total = bytes_written + this_len

                    # 續傳重新計時進度
                    last_progress_t = time.monotonic()

        # 大小檢查（若知道總長）
        if expected_total is not None and bytes_written != expected_total:
            raise RequestException(f"大小不符：預期 {expected_total} 實得 {bytes_written}")

        os.replace(tmp, dst)
        # 清除 meta
        try:
            if os.path.exists(meta_path):
                os.remove(meta_path)
        except Exception:
            pass

        print(f"成功下載：{dst}")
        manifest["items"][recording_id]["status"] = "completed"
        manifest["items"][recording_id]["downloaded"] = bytes_written
        _save_manifest(manifest)
        return True

    except (Timeout, RequestException) as e:
        print(f"下載失敗（{filename}）：{e}")
        manifest["items"][recording_id]["status"] = "failed"
        manifest["items"][recording_id]["downloaded"] = bytes_written
        _save_manifest(manifest)
        # 更新 meta 為 failed（保留 .part 以便下次續傳）
        _write_meta(meta_path, {
            "id": recording_id,
            "filename": filename,
            "url": url,
            "expected_total": expected_total,
            "bytes_written": bytes_written,
            "status": "failed"
        })
    except Exception as e:
        print(f"下載異常（{filename}）：{e}")
        manifest["items"][recording_id]["status"] = "failed"
        manifest["items"][recording_id]["downloaded"] = bytes_written
        _save_manifest(manifest)
        _write_meta(meta_path, {
            "id": recording_id,
            "filename": filename,
            "url": url,
            "expected_total": expected_total,
            "bytes_written": bytes_written,
            "status": "failed"
        })
    finally:
        # 若失敗，保留 .part 以便下次續傳
        pass

    return False


def download_all_recordings():
    recs = get_all_recordings()
    if not recs:
        print("沒有找到任何錄音。")
        return {"ok": [], "failed": [], "skipped": []}

    print(f"找到 {len(recs)} 個錄音。")

    ok_ids, failed_ids, skipped_ids = [], [], []

    # 若目錄中已經有完整檔案，就略過；有 .part 就續傳
    for r in recs:
        rid = str(r["id"])
        filename = r["filename"]
        dst = os.path.join(DOWNLOAD_DIR, filename)
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            print(f"略過：{filename} (id={rid}) 已存在")
            skipped_ids.append(rid)
            continue

        if download_recording(r):
            ok_ids.append(rid)
        else:
            failed_ids.append(rid)

    print(f"完成：成功 {len(ok_ids)}/{len(recs)}，失敗 {len(failed_ids)}，略過 {len(skipped_ids)}")
    if failed_ids:
        print("失敗的 recording_id：", ", ".join(failed_ids))
        print("你也可以用 list_incomplete_parts() 檢查殘留的 .part 對應 id")
    return {"ok": ok_ids, "failed": failed_ids, "skipped": skipped_ids}


if __name__ == "__main__":
    summary = download_all_recordings()
    # 範例：只重試失敗的那些
    if summary["failed"]:
        print("開始重試失敗的項目...")
        # 重新 call get_all_recordings，篩出 id 在 failed 清單的再跑一次
        all_recs = get_all_recordings()
        retry_recs = [r for r in all_recs if str(r["id"]) in set(summary["failed"])]
        for r in retry_recs:
            download_recording(r)
        print("重試結束。")

    # failed_ids = {
    #     30, 90, 149, 184, 243, 303, 359, 402, 452, 512, 572, 627, 688, 746, 806,
    #     867, 925, 978, 989, 1044, 1104, 1163, 1223, 1282, 1341, 1399, 1516, 1567,
    #     1618, 1623, 1683, 1741, 1800, 1857, 1914, 1963, 2025, 2071, 2081, 2140,
    #     2168, 2223, 2283, 2391, 2448, 2508, 2556, 2563, 2620, 2677, 2734, 2784,
    #     2842, 2865, 2925, 2983, 3029, 3087
    # }
    # # 取回最新清單並過濾到需要重抓的
    # all_recs = get_all_recordings()
    # by_id = {int(r["id"]): r for r in all_recs}
    # retry_recs = [by_id[i] for i in failed_ids if i in by_id]
    #
    # print(f"開始重試 {len(retry_recs)} 個失敗項目...")
    # ok = 0
    # for r in retry_recs:
    #     ok += 1 if download_recording(r) else 0
    # print(f"重試完成：成功 {ok}/{len(retry_recs)}")

