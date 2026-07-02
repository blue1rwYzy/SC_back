"""
测试视频数据库接口
直接访问 http://localhost:8001/videos/database
"""
import requests
import json

print("\n" + "="*60)
print("测试视频数据库接口")
print("="*60)

url = "http://localhost:8001/videos/database"
print(f"\n请求 URL: {url}")

try:
    response = requests.get(url, timeout=10)

    print(f"\n响应状态码: {response.status_code}")
    print(f"响应头: {dict(response.headers)}")

    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ 请求成功！")
        print(f"\n返回数据结构:")
        print(json.dumps(data, indent=2, ensure_ascii=False))

        if data.get("code") == 0:
            video_list = data.get("data", [])
            print(f"\n📊 统计信息:")
            print(f"   视频总数: {len(video_list)}")

            if video_list:
                print(f"\n📹 视频列表:")
                for i, video in enumerate(video_list[:5], 1):  # 只显示前5个
                    print(f"\n   {i}. {video.get('filename', 'N/A')}")
                    print(f"      路径: {video.get('path', 'N/A')}")
                    print(f"      大小: {video.get('size', 0) / 1024 / 1024:.2f} MB")
                    print(f"      上传时间: {video.get('uploadedAt', 'N/A')}")

                if len(video_list) > 5:
                    print(f"\n   ... 还有 {len(video_list) - 5} 个视频")
            else:
                print(f"\n⚠️ 返回的视频列表为空")
                print(f"   消息: {data.get('message', 'N/A')}")
        else:
            print(f"\n❌ API 返回错误码: {data.get('code')}")
            print(f"   消息: {data.get('message', 'N/A')}")
    else:
        print(f"\n❌ HTTP 请求失败")
        print(f"响应内容: {response.text}")

except requests.exceptions.ConnectionError:
    print(f"\n❌ 连接失败！")
    print(f"\n可能的原因:")
    print(f"1. business-service 未在 8001 端口运行")
    print(f"2. 服务启动失败")
    print(f"\n请检查:")
    print(f"1. 运行 'netstat -ano | findstr :8001' 确认端口监听")
    print(f"2. 查看 business-service 控制台是否有错误")

except Exception as e:
    print(f"\n❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
