import requests
import json

# 設置服務器 URL
# SERVER_URL = 'http://163.18.22.51:88'
SERVER_URL = 'http://192.168.31.66:5000/'


def get_all_recordings():
    """
    獲取所有錄音的列表
    """
    response = requests.get(f"{SERVER_URL}/recordings")
    if response.status_code == 200:
        return response.json()
    else:
        print(f"獲取錄音列表失敗。錯誤: {response.text}")
        return []


def delete_recording(recording_id):
    """
    刪除單個錄音
    """
    response = requests.post(f"{SERVER_URL}/delete/{recording_id}")
    if response.status_code == 200:
        print(f"成功刪除錄音 ID: {recording_id}")
    else:
        print(f"刪除錄音 ID: {recording_id} 失敗。錯誤: {response.text}")


def delete_all_recordings():
    """
    刪除所有錄音
    """
    recordings = get_all_recordings()
    if not recordings:
        print("沒有找到任何錄音。")
        return

    print(f"從 {SERVER_URL} 上。")
    print(f"找到 {len(recordings)} 個錄音。")
    confirm = input("您確定要刪除所有錄音嗎？此操作不可逆。 (y/n): ")

    if confirm.lower() != 'y':
        print("操作已取消")
        return

    for recording in recordings:
        delete_recording(recording['id'])

    print("所有錄音刪除完成。")


if __name__ == "__main__":
    delete_all_recordings()