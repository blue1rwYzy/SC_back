"""
测试推理结果是否正确保存到 MinIO
"""
import requests
import json

print("\n" + "="*60)
print("测试推理结果保存情况")
print("="*60)

# 1. 查询最新的推理批次
print("\n1. 查询推理批次...")
try:
    response = requests.get("http://127.0.0.1:8001/inference-results/batches")
    batches = response.json()
    print(f"   状态码: {response.status_code}")

    if batches.get('code') == 0 and batches.get('data'):
        batch_list = batches['data']
        print(f"   找到 {len(batch_list)} 个批次")

        if batch_list:
            latest_batch = batch_list[0]
            batch_name = latest_batch['batchName']
            print(f"   最新批次: {batch_name}")

            # 2. 查询该批次的详细结果
            print(f"\n2. 查询批次 {batch_name} 的结果...")
            response2 = requests.get(f"http://127.0.0.1:8001/inference-results/batch/{batch_name}")
            batch_data = response2.json()

            if batch_data.get('code') == 0:
                results = batch_data['data']['results']
                print(f"   找到 {len(results)} 个结果")

                if results:
                    result = results[0]
                    print(f"\n3. 第一个结果详情:")
                    print(f"   原图: {result['originalImage']}")
                    print(f"   结果图: {result['resultImage']}")
                    print(f"   原图相对路径: {result['originalImageRel']}")
                    print(f"   结果图相对路径: {result['resultImageRel']}")

                    # 3. 测试访问结果图
                    result_image_rel = result['resultImageRel']
                    test_url = f"http://127.0.0.1:8001/uploads/img_results/{result_image_rel}"

                    print(f"\n4. 测试访问结果图:")
                    print(f"   URL: {test_url}")

                    response3 = requests.get(test_url, allow_redirects=False)
                    print(f"   状态码: {response3.status_code}")

                    if response3.status_code == 307:
                        print(f"   ✅ 重定向到: {response3.headers.get('location', 'N/A')[:100]}...")

                        # 跟随重定向
                        response4 = requests.get(test_url, allow_redirects=True)
                        if response4.status_code == 200:
                            content_type = response4.headers.get('content-type', '')
                            size = len(response4.content)
                            print(f"   ✅ 成功获取图片: {content_type}, {size} bytes")
                        else:
                            print(f"   ❌ 跟随重定向失败: {response4.status_code}")
                    elif response3.status_code == 404:
                        print(f"   ❌ 图片不存在于 MinIO")
                    else:
                        print(f"   ⚠️ 未预期的状态码")
            else:
                print(f"   ❌ 查询批次失败: {batch_data}")
    else:
        print(f"   ❌ 未找到批次: {batches}")

except Exception as e:
    print(f"   ❌ 错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
