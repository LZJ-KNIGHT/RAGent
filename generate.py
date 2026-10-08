import csv
import random

# 参数设置
num_rows = 100  # 数据行数
mean = 0        # 正态分布的均值
std_dev = 0.7   # 正态分布的标准差

# 生成数据
data = []
for i in range(num_rows):
    value = random.gauss(mean, std_dev)  # 使用正态分布生成随机数
    data.append((i + 1, value))  # id 从 1 开始递增

# 写入 CSV 文件
csv_file_path = "test.csv"
with open(csv_file_path, mode="w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(["id", "value"])  # 写入表头
    writer.writerows(data)           # 写入数据

print(f"CSV 文件已生成: {csv_file_path}")