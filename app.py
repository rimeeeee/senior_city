import os

from flask import Flask, request, jsonify, make_response, render_template
import pandas as pd
import json
from flask_cors import CORS

# import mysql.connector
# from sqlalchemy import create_engine

# # MySQL 접속 정보 (Railway 환경변수에서 받아옴)
# db_config = {
#     "host": os.getenv("DB_HOST", "mysql.railway.internal"),
#     "user": os.getenv("DB_USER", "root"),
#     "password": os.getenv("DB_PASSWORD", "eBkFflFRICnvSVmRZcJCZIabKDwkVsKK"),
#     "database": os.getenv("DB_NAME", "railway"),
#     "port": int(os.getenv("DB_PORT", 3306))
# }
#
# # mysql.connector 방식
# def get_connection():
#     return mysql.connector.connect(**db_config)
#
# # SQLAlchemy 방식
# engine = create_engine(
#     f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}/{db_config['database']}"
# )

app = Flask(__name__)
CORS(app)

# 데이터 로딩

df = pd.read_csv('final_df.csv', encoding='utf-8')  # 자치구별 노인친화 지표
#df = df.iloc[2:].reset_index(drop=True)  # 데이터 시작 행 정리
df["자치구"] = df["district"]  # 자치구 이름 정리

#df.to_sql(name = 'district_data', con=engine, if_exists="append", index=False)

# 카테고리와 실제 컬럼 매핑
CATEGORY_COLUMNS = {
    "safety": ["crime_rate"],
    "walk": ["senior_pedestrian_accidents", "steep_slope_count"],
    "relation": ["senior_center"],
    "welfare": ["sports_center", "welfare_facilities"],
    "culture": ["cultural_facilities"],
    "transport": ["subway_station_count", "bus_stop_density"],
    "medical": ["medical_corporations_count", "emergency_room_count"],
    "social": ["employ"],
    "nature": ["green_space_per_capita"],
    "air": ["pm2_5_level"]
}

#안전:'crime_rate'
#보행환경:'senior_pedestrian_accidents','steep_slope_count'
#관계:'senior_center'
#복지:'sports_center','welfare_facilities'
#문화:'cultural_facilities'
#대중교통:'subway_station_count','bus_stop_density'
#의료:'medical_corporations_count','emergency_room_count'
#사회참여:'employ'
#자연:'green_space_per_capita'
#대기환경:'pm2.5_level'


# 점수 계산 함수
def calculate_scores(weights,byNum ):
    features = list(weights.keys())
    weights_series = pd.Series(weights)


    # 선택한 지표만 추출
    df_selected = df[features]

    # 가중치 곱한 후 점수 계산
    df["score"] = df_selected.mul(weights_series).sum(axis=1)

    # 상위 n개 구 반환
    result = df[["자치구", "score"]].sort_values(by="score", ascending=False).head(byNum)
    return result.to_dict(orient="records")


@app.route("/")
def index():
    return render_template('index.html')

# API 라우팅

# 사용자 가중치 API
@app.route("/recommend")
def recommend():
    try:
        num = int(request.args.get("num", 5))
        weights = {}

        # 카테고리 파싱
        for category, cols in CATEGORY_COLUMNS.items():
            if category in request.args:
                try:
                    weight = float(request.args.get(category))
                    for col in cols:
                        weights[col] = weight
                except ValueError:
                    continue

        if not weights:
            return jsonify({"error": "가중치 입력이 필요합니다."}), 400

        # 반전해야 할 지표
        INVERTED_COLS = ["crime_rate", "senior_pedestrian_accidents", "steep_slope_count", "pm2.5_level"]

        # 가중치 적용용 복사본 생성
        df_weighted = df.copy()
        for col in weights:
            if col in INVERTED_COLS:
                df_weighted[col] = 1 - pd.to_numeric(df_weighted[col], errors="coerce")
            else:
                df_weighted[col] = pd.to_numeric(df_weighted[col], errors="coerce")

        df_numeric = df_weighted[list(weights.keys())]
        score = df_numeric.mul(pd.Series(weights)).sum(axis=1)

        df_result = df.copy()
        df_result["score"] = score

        result = (
            df_result[["district", "score"]]
            .sort_values(by="score", ascending=False)
            .head(num)
            .to_dict(orient="records")
        )

        response = make_response(json.dumps({"result": result}, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 400


# F-28 – 동네 안전이 제일 중요한 어르신
@app.route("/safety-priority")
def safety_priority():
    try:
        # 안전 관련 지표: 낮을수록 안전함
        safety_cols = ["crime_rate", "senior_pedestrian_accidents"]

        df_subset = df[["district"] + safety_cols].copy()
        df_subset["safety_score"] = df_subset[safety_cols].mean(axis=1)

        result = (
            df_subset[["district", "safety_score"]]
            .sort_values(by="safety_score", ascending=True)
            .head(5)
            .to_dict(orient="records")
        )

        response = make_response(json.dumps({
            "title": "안전한 동네 TOP 5",
            "unit": "범죄율 + 노인 보행자 사고 (낮을수록 안전)",
            "category": "safety",
            "items": [
                { "rank": i + 1, "name": row["district"], "score": round(row["safety_score"], 3) }
                for i, row in enumerate(result)
            ]
        }, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 400

#F-29 – 보행 취약 지형이 적은 지역 추천
@app.route("/walkability-priority")
def walkability_priority():
    try:
        # 보행 환경 기준: 낮을수록 좋은 급경사지 수
        df_subset = df[["district", "steep_slope_count"]].copy()
        df_subset["walk_score"] = df_subset["steep_slope_count"]

        result = (
            df_subset[["district", "walk_score"]]
            .sort_values(by="walk_score", ascending=True)
            .head(5)
            .to_dict(orient="records")
        )

        response = make_response(json.dumps({
            "title": "보행 환경이 좋은 동네 TOP 5",
            "unit": "급경사지 개수 (낮을수록 보행에 유리)",
            "category": "walk",
            "items": [
                { "rank": i + 1, "name": row["district"], "score": row["walk_score"] }
                for i, row in enumerate(result)
            ]
        }, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 400

#F-30 – 대중교통 이용이 편리한 자치구
@app.route("/transport-priority")
def transport_priority():
    try:
        # 관련 지표: 지하철역 수 + 버스 정류장 밀도
        cols = ["subway_station_count", "bus_stop_density"]
        df_subset = df[["district"] + cols].copy()
        df_subset["transport_score"] = df_subset[cols].mean(axis=1)

        result = (
            df_subset[["district", "transport_score"]]
            .sort_values(by="transport_score", ascending=False)
            .head(5)
            .to_dict(orient="records")
        )

        response = make_response(json.dumps({
            "title": "대중교통 접근성이 좋은 동네 TOP 5",
            "unit": "지하철역 수 + 버스 정류장 밀도 평균",
            "category": "transport",
            "items": [
                { "rank": i + 1, "name": row["district"], "score": round(row["transport_score"], 3) }
                for i, row in enumerate(result)
            ]
        }, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 400


#F-31 – 병원 접근성이 중요한 어르신을 위한 추천
@app.route("/medical-priority")
def medical_priority():
    try:
        # 관련 지표: 의료법인 수 + 응급실 수
        cols = ["medical_corporations_count", "emergency_room_count"]
        df_subset = df[["district"] + cols].copy()
        df_subset["medical_score"] = df_subset[cols].mean(axis=1)

        result = (
            df_subset[["district", "medical_score"]]
            .sort_values(by="medical_score", ascending=False)
            .head(5)
            .to_dict(orient="records")
        )

        response = make_response(json.dumps({
            "title": "의료 접근성이 좋은 동네 TOP 5",
            "unit": "의료법인 수 + 응급실 수 평균",
            "category": "medical",
            "items": [
                { "rank": i + 1, "name": row["district"], "score": round(row["medical_score"], 3) }
                for i, row in enumerate(result)
            ]
        }, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 400

#F-32 – 친목 모임을 좋아하시는 어르신을 위한 추천
@app.route("/social-priority")
def social_priority():
    try:
        df_subset = df[["district", "senior_center"]].copy()
        df_subset["social_score"] = df_subset["senior_center"]

        result = (
            df_subset[["district", "social_score"]]
            .sort_values(by="social_score", ascending=False)
            .head(5)
            .to_dict(orient="records")
        )

        response = make_response(json.dumps({
            "title": "친목 활동하기 좋은 동네 TOP 5",
            "unit": "경로당 수",
            "category": "social",
            "items": [
                { "rank": i + 1, "name": row["district"], "score": int(row["social_score"]) }
                for i, row in enumerate(result)
            ]
        }, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 400


#F-33 – 건강한 취미 생활을 즐기시는 어르신을 위한 추천
@app.route("/culture-welfare-priority")
def culture_welfare_priority():
    try:
        cols = ["welfare_facilities", "cultural_facilities"]
        df_subset = df[["district"] + cols].copy()
        df_subset["culture_score"] = df_subset[cols].mean(axis=1)

        result = (
            df_subset[["district", "culture_score"]]
            .sort_values(by="culture_score", ascending=False)
            .head(5)
            .to_dict(orient="records")
        )

        response = make_response(json.dumps({
            "title": "취미·문화생활 하기 좋은 동네 TOP 5",
            "unit": "복지시설 + 문화시설 평균",
            "category": "culture",
            "items": [
                { "rank": i + 1, "name": row["district"], "score": round(row["culture_score"], 3) }
                for i, row in enumerate(result)
            ]
        }, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 400

#F-34 – 산책·운동을 즐기시는 어르신을 위한 추천
@app.route("/walk-sports-priority")
def walk_sports_priority():
    try:
        cols = ["sports_center"]
        df_subset = df[["district"] + cols].copy()
        df_subset["activity_score"] = df_subset[cols].mean(axis=1)

        result = (
            df_subset[["district", "activity_score"]]
            .sort_values(by="activity_score", ascending=False)
            .head(5)
            .to_dict(orient="records")
        )

        response = make_response(json.dumps({
            "title": "산책·운동하기 좋은 동네 TOP 5",
            "unit": "체육시설 수",
            "category": "activity",
            "items": [
                { "rank": i + 1, "name": row["district"], "score": round(row["activity_score"], 3) }
                for i, row in enumerate(result)
            ]
        }, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 400


#F-69 – 자연환경을 중요시하는 어르신을 위한 추천
@app.route("/nature-priority")
def nature_priority():
    try:
        df_subset = df[["district", "green_space_per_capita"]].copy()
        df_subset["nature_score"] = df_subset["green_space_per_capita"]

        result = (
            df_subset[["district", "nature_score"]]
            .sort_values(by="nature_score", ascending=False)
            .head(5)
            .to_dict(orient="records")
        )

        response = make_response(json.dumps({
            "title": "자연환경이 좋은 동네 TOP 5",
            "unit": "1인당 녹지면적",
            "category": "nature",
            "items": [
                { "rank": i + 1, "name": row["district"], "score": round(row["nature_score"], 3) }
                for i, row in enumerate(result)
            ]
        }, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 400


#F-10 고령친화 자치구 추천
@app.route("/senior-friendly-top5")
def senior_friendly_top5():
    try:
        CATEGORY_COLUMNS = {
            "안전": ["crime_rate"],
            "보행환경": ["senior_pedestrian_accidents", "steep_slope_count"],
            "관계": ["senior_center"],
            "복지": ["sports_center", "welfare_facilities"],
            "문화": ["cultural_facilities"],
            "대중교통": ["subway_station_count", "bus_stop_density"],
            "의료": ["medical_corporations_count", "emergency_room_count"],
            "사회참여": ["employ"],
            "자연": ["green_space_per_capita"],
            "대기환경": ["pm2_5_level"]
        }

        category_labels = {
            "안전": "치안이 가장 좋은",
            "보행환경": "보행환경이 가장 좋은",
            "관계": "경로당이 가장 많은",
            "복지": "복지시설이 가장 많은",
            "문화": "문화시설이 가장 많은",
            "대중교통": "대중교통이 가장 편리한",
            "의료": "의료 접근성이 가장 좋은",
            "사회참여": "노인 일자리가 가장 많은",
            "자연": "녹지가 가장 많은",
            "대기환경": "대기환경이 가장 좋은"
        }

        df_copy = df.copy()
        scores = {}

        for cat, cols in CATEGORY_COLUMNS.items():
            values = df_copy[cols].copy()
            if cat in ["안전", "보행환경", "대기환경"]:
                values = 1 - values
            scores[cat] = values.mean(axis=1)

        df_copy["total_score"] = pd.DataFrame(scores).mean(axis=1)
        top5 = df_copy.copy()
        top5["total_score"] = df_copy["total_score"]
        top5 = top5.sort_values(by="total_score", ascending=False).head(5)

        avg_scores = {}
        for k, cols in CATEGORY_COLUMNS.items():
            temp_df = df[cols].copy()
            if k in ["안전", "보행환경", "대기환경"]:
                temp_df = 1 - temp_df
            avg_scores[k] = round(temp_df.mean(axis=1).mean(), 3)

        result = []
        for idx, row in enumerate(top5.itertuples(), start=1):
            district_name = getattr(row, "district")

            # metricData 생성
            metric_data = []
            for cat, cols in CATEGORY_COLUMNS.items():
                selected = df[df["district"] == district_name][cols].mean(axis=1).values[0]
                if cat in ["안전", "보행환경", "대기환경"]:
                    selected = 1 - selected
                metric_data.append({
                    "name": cat,
                    "selectedDistrict": round(selected, 3),
                    "average": avg_scores[cat]
                })

            # 설명 문장: 가장 두드러진 항목
            max_diff = -float("inf")
            best_cat = None
            for cat in CATEGORY_COLUMNS:
                district_val = [m["selectedDistrict"] for m in metric_data if m["name"] == cat][0]
                diff = district_val - avg_scores[cat]
                if diff > max_diff:
                    max_diff = diff
                    best_cat = cat

            result.append({
                "district": district_name,
                "rank": idx,
                "metricData": metric_data,
                "info": f"{district_name}는 {category_labels[best_cat]} 동네입니다."
            })

        response = make_response(json.dumps({"data": result}, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({ "error": str(e) }), 500


#F-11 – 고령 비친화 자치구 하위 5개
@app.route("/senior-unfriendly-top5")
def senior_unfriendly_top5():
    try:
        CATEGORY_COLUMNS = {
            "안전": ["crime_rate"],
            "보행환경": ["senior_pedestrian_accidents", "steep_slope_count"],
            "관계": ["senior_center"],
            "복지": ["sports_center", "welfare_facilities"],
            "문화": ["cultural_facilities"],
            "대중교통": ["subway_station_count", "bus_stop_density"],
            "의료": ["medical_corporations_count", "emergency_room_count"],
            "사회참여": ["employ"],
            "자연": ["green_space_per_capita"],
            "대기환경": ["pm2_5_level"]
        }

        category_labels = {
            "안전": "치안이 가장 부족한",
            "보행환경": "보행환경이 가장 열악한",
            "관계": "경로당이 가장 적은",
            "복지": "복지시설이 가장 부족한",
            "문화": "문화시설이 가장 적은",
            "대중교통": "대중교통 접근성이 가장 낮은",
            "의료": "의료 접근성이 가장 부족한",
            "사회참여": "노인 일자리가 가장 부족한",
            "자연": "녹지가 가장 적은",
            "대기환경": "대기질이 가장 나쁜"
        }

        df_copy = df.copy()
        scores = {}

        for cat, cols in CATEGORY_COLUMNS.items():
            values = df_copy[cols].copy()
            if cat in ["안전", "보행환경", "대기환경"]:
                values = 1 - values
            scores[cat] = values.mean(axis=1)

        df_copy["total_score"] = pd.DataFrame(scores).mean(axis=1)
        bottom5 = df_copy.copy()
        bottom5["total_score"] = df_copy["total_score"]
        bottom5 = bottom5.sort_values(by="total_score", ascending=True).head(5)

        avg_scores = {}
        for k, cols in CATEGORY_COLUMNS.items():
            temp_df = df[cols].copy()
            if k in ["안전", "보행환경", "대기환경"]:
                temp_df = 1 - temp_df
            avg_scores[k] = round(temp_df.mean(axis=1).mean(), 3)

        result = []
        for idx, row in enumerate(bottom5.itertuples(), start=1):
            district_name = getattr(row, "district")

            metric_data = []
            for cat, cols in CATEGORY_COLUMNS.items():
                selected = df[df["district"] == district_name][cols].mean(axis=1).values[0]
                if cat in ["안전", "보행환경", "대기환경"]:
                    selected = 1 - selected
                metric_data.append({
                    "name": cat,
                    "selectedDistrict": round(selected, 3),
                    "average": avg_scores[cat]
                })

            # 가장 부족한 지표 = 평균 대비 차이가 가장 큰 음수
            min_diff = float("inf")
            worst_cat = None
            for cat in CATEGORY_COLUMNS:
                district_val = [m["selectedDistrict"] for m in metric_data if m["name"] == cat][0]
                diff = district_val - avg_scores[cat]
                if diff < min_diff:
                    min_diff = diff
                    worst_cat = cat

            result.append({
                "district": district_name,
                "rank": idx,
                "metricData": metric_data,
                "info": f"{district_name}는 {category_labels[worst_cat]} 동네입니다."
            })

        # ensure_ascii=False로 응답
        response = make_response(json.dumps({ "data": result }, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ✅ 통합 API: 카테고리별 상위 5개 자치구 조회
@app.route("/top5-by-category")
def top5_by_category():
    try:
        category_name = request.args.get("category")
        if not category_name:
            return jsonify({"error": "카테고리명을 전달해주세요."}), 400

        CATEGORY_COLUMNS = {
            "치안": ["crime_rate"],
            "보행환경": ["senior_pedestrian_accidents", "steep_slope_count"],
            "대중교통": ["subway_station_count", "bus_stop_density"],
            "병원접근성": ["medical_corporations_count", "emergency_room_count"],
            "노인복지시설": ["welfare_facilities", "sports_center"],
            "문화시설": ["cultural_facilities"],
            "경로당": ["senior_center"],
            "노인일자리": ["employ"],
            "대기환경": ["pm2_5_level"],
            "자연환경": ["green_space_per_capita"]
        }

        REVERSE_COLUMNS = ["crime_rate", "senior_pedestrian_accidents", "steep_slope_count", "pm2_5_level"]



        if category_name not in CATEGORY_COLUMNS:
            return jsonify({"error": f"{category_name}은 유효하지 않은 카테고리입니다."}), 400

        cols = CATEGORY_COLUMNS[category_name]
        df_copy = df[["district"] + cols].copy()

        for col in cols:
            if col in REVERSE_COLUMNS:
                df_copy[col] = 1 - df_copy[col]

        df_copy["score"] = df_copy[cols].mean(axis=1)
        df_top = df_copy.sort_values(by="score", ascending=False).head(5).reset_index(drop=True)

        avg_val = df_copy["score"].mean()

        items = []
        for i, row in df_top.iterrows():
            items.append({
                "district": row["district"],
                "rank": i + 1,
                "score": round(row["score"], 3),
                "average": round(avg_val, 3)

            })

        response = make_response(json.dumps({"data": items}, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# #F-12 – 치안이 좋은 자치구 TOP 5
# @app.route("/safety-top5")
# def safety_top5():
#     try:
#         df_subset = df[["district", "crime_rate"]].copy()
#         df_subset["safety_score"] = 1 - pd.to_numeric(df_subset["crime_rate"], errors="coerce")
#
#         result = (
#             df_subset[["district", "safety_score"]]
#             .sort_values(by="safety_score", ascending=False)
#             .head(5)
#             .to_dict(orient="records")
#         )
#
#         response = make_response(json.dumps({
#             "title": "치안이 좋은 자치구 TOP 5",
#             "unit": "범죄율 (낮을수록 치안이 좋음)",
#             "category": "safety",
#             "items": [
#                 { "rank": i + 1, "name": row["district"], "score": round(row["safety_score"], 3) }
#                 for i, row in enumerate(result)
#             ]
#         }, ensure_ascii=False))
#         response.headers["Content-Type"] = "application/json; charset=utf-8"
#         return response
#
#     except Exception as e:
#         return jsonify({"error": str(e)}), 400
#
# #F-13 – 보행환경이 좋은 자치구 TOP 5
# @app.route("/walkenv-top5")
# def walkenv_top5():
#     try:
#         cols = ["senior_pedestrian_accidents", "steep_slope_count"]
#         df_subset = df[["district"] + cols].copy()
#         for col in cols:
#             df_subset[col] = 1 - pd.to_numeric(df_subset[col], errors="coerce")
#
#         df_subset["walkenv_score"] = df_subset[cols].mean(axis=1)
#
#         result = (
#             df_subset[["district", "walkenv_score"]]
#             .sort_values(by="walkenv_score", ascending=False)
#             .head(5)
#             .to_dict(orient="records")
#         )
#
#         response = make_response(json.dumps({
#             "title": "보행환경이 좋은 자치구 TOP 5",
#             "unit": "보행자 사고/급경사지 (낮을수록 좋음)",
#             "category": "walkenv",
#             "items": [
#                 { "rank": i + 1, "name": row["district"], "score": round(row["walkenv_score"], 3) }
#                 for i, row in enumerate(result)
#             ]
#         }, ensure_ascii=False))
#         response.headers["Content-Type"] = "application/json; charset=utf-8"
#         return response
#
#     except Exception as e:
#         return jsonify({"error": str(e)}), 400
#
# #F-14 – 대중교통이 잘되어있는 자치구 TOP 5
# @app.route("/transport-top5")
# def transport_top5():
#     try:
#         cols = ["subway_station_count", "bus_stop_density"]
#         df_subset = df[["district"] + cols].copy()
#         for col in cols:
#             df_subset[col] = pd.to_numeric(df_subset[col], errors="coerce")
#
#         df_subset["transport_score"] = df_subset[cols].mean(axis=1)
#
#         result = (
#             df_subset[["district", "transport_score"]]
#             .sort_values(by="transport_score", ascending=False)
#             .head(5)
#             .to_dict(orient="records")
#         )
#
#         response = make_response(json.dumps({
#             "title": "대중교통이 잘되어있는 자치구 TOP 5",
#             "unit": "지하철역 수 + 정류장 밀도 평균",
#             "category": "transport",
#             "items": [
#                 { "rank": i + 1, "name": row["district"], "score": round(row["transport_score"], 3) }
#                 for i, row in enumerate(result)
#             ]
#         }, ensure_ascii=False))
#         response.headers["Content-Type"] = "application/json; charset=utf-8"
#         return response
#
#     except Exception as e:
#         return jsonify({"error": str(e)}), 400
#
# #F-15 – 병원 접근성이 좋은 자치구 TOP 5
# @app.route("/medical-top5")
# def medical_top5():
#     try:
#         cols = ["medical_corporations_count", "emergency_room_count"]
#         df_subset = df[["district"] + cols].copy()
#         for col in cols:
#             df_subset[col] = pd.to_numeric(df_subset[col], errors="coerce")
#
#         df_subset["medical_score"] = df_subset[cols].mean(axis=1)
#
#         result = (
#             df_subset[["district", "medical_score"]]
#             .sort_values(by="medical_score", ascending=False)
#             .head(5)
#             .to_dict(orient="records")
#         )
#
#         response = make_response(json.dumps({
#             "title": "병원 접근성이 좋은 자치구 TOP 5",
#             "unit": "의료법인 수 + 응급실 수 평균",
#             "category": "medical",
#             "items": [
#                 { "rank": i + 1, "name": row["district"], "score": round(row["medical_score"], 3) }
#                 for i, row in enumerate(result)
#             ]
#         }, ensure_ascii=False))
#         response.headers["Content-Type"] = "application/json; charset=utf-8"
#         return response
#
#     except Exception as e:
#         return jsonify({"error": str(e)}), 400
#
#
# #F-16 – 노인복지시설이 많은 자치구 TOP 5
# @app.route("/welfare-top5")
# def welfare_top5():
#     try:
#         cols = ["welfare_facilities", "sports_center"]
#         df_subset = df[["district"] + cols].copy()
#         for col in cols:
#             df_subset[col] = pd.to_numeric(df_subset[col], errors="coerce")
#
#         df_subset["welfare_score"] = df_subset[cols].mean(axis=1)
#
#         result = (
#             df_subset[["district", "welfare_score"]]
#             .sort_values(by="welfare_score", ascending=False)
#             .head(5)
#             .to_dict(orient="records")
#         )
#
#         response = make_response(json.dumps({
#             "title": "노인복지시설이 많은 자치구 TOP 5",
#             "unit": "노인복지시설 수 + 공공체육시설 수 평균",
#             "category": "welfare",
#             "items": [
#                 { "rank": i + 1, "name": row["district"], "score": round(row["welfare_score"], 3) }
#                 for i, row in enumerate(result)
#             ]
#         }, ensure_ascii=False))
#         response.headers["Content-Type"] = "application/json; charset=utf-8"
#         return response
#
#     except Exception as e:
#         return jsonify({"error": str(e)}), 400
#
#
# #F-60 – 문화시설이 많은 자치구 TOP 5
# @app.route("/culture-top5")
# def culture_top5():
#     try:
#         df_subset = df[["district", "cultural_facilities"]].copy()
#         df_subset["culture_score"] = pd.to_numeric(df_subset["cultural_facilities"], errors="coerce")
#
#         result = (
#             df_subset[["district", "culture_score"]]
#             .sort_values(by="culture_score", ascending=False)
#             .head(5)
#             .to_dict(orient="records")
#         )
#
#         response = make_response(json.dumps({
#             "title": "문화시설이 많은 자치구 TOP 5",
#             "unit": "문화시설 수",
#             "category": "culture",
#             "items": [
#                 { "rank": i + 1, "name": row["district"], "score": round(row["culture_score"], 3) }
#                 for i, row in enumerate(result)
#             ]
#         }, ensure_ascii=False))
#         response.headers["Content-Type"] = "application/json; charset=utf-8"
#         return response
#
#     except Exception as e:
#         return jsonify({"error": str(e)}), 400
#
#
# #F-61 – 경로당이 많은 자치구 TOP 5
# @app.route("/senior-center-top5")
# def senior_center_top5():
#     try:
#         df_subset = df[["district", "senior_center"]].copy()
#         df_subset["senior_center_score"] = pd.to_numeric(df_subset["senior_center"], errors="coerce")
#
#         result = (
#             df_subset[["district", "senior_center_score"]]
#             .sort_values(by="senior_center_score", ascending=False)
#             .head(5)
#             .to_dict(orient="records")
#         )
#
#         response = make_response(json.dumps({
#             "title": "경로당이 많은 자치구 TOP 5",
#             "unit": "경로당 수",
#             "category": "relation",
#             "items": [
#                 { "rank": i + 1, "name": row["district"], "score": round(row["senior_center_score"], 3) }
#                 for i, row in enumerate(result)
#             ]
#         }, ensure_ascii=False))
#         response.headers["Content-Type"] = "application/json; charset=utf-8"
#         return response
#
#     except Exception as e:
#         return jsonify({"error": str(e)}), 400
#
# #F-62 – 노인 일자리가 많은 자치구 TOP 5
# @app.route("/employment-top5")
# def employment_top5():
#     try:
#         df_subset = df[["district", "employ"]].copy()
#         df_subset["employment_score"] = pd.to_numeric(df_subset["employ"], errors="coerce")
#
#         result = (
#             df_subset[["district", "employment_score"]]
#             .sort_values(by="employment_score", ascending=False)
#             .head(5)
#             .to_dict(orient="records")
#         )
#
#         response = make_response(json.dumps({
#             "title": "노인 일자리가 많은 자치구 TOP 5",
#             "unit": "노인 일자리 수",
#             "category": "employment",
#             "items": [
#                 { "rank": i + 1, "name": row["district"], "score": round(row["employment_score"], 3) }
#                 for i, row in enumerate(result)
#             ]
#         }, ensure_ascii=False))
#         response.headers["Content-Type"] = "application/json; charset=utf-8"
#         return response
#
#     except Exception as e:
#         return jsonify({"error": str(e)}), 400
#
#
# #F-63 – 대기환경이 좋은 자치구 TOP 5
# @app.route("/air-top5")
# def air_top5():
#     try:
#         df_subset = df[["district", "pm2_5_level"]].copy()
#         df_subset["air_score"] = 1 - pd.to_numeric(df_subset["pm2_5_level"], errors="coerce")
#
#         result = (
#             df_subset[["district", "air_score"]]
#             .sort_values(by="air_score", ascending=False)
#             .head(5)
#             .to_dict(orient="records")
#         )
#
#         response = make_response(json.dumps({
#             "title": "대기환경이 좋은 자치구 TOP 5",
#             "unit": "초미세먼지 반전 점수 (낮을수록 좋음)",
#             "category": "air",
#             "items": [
#                 { "rank": i + 1, "name": row["district"], "score": round(row["air_score"], 3) }
#                 for i, row in enumerate(result)
#             ]
#         }, ensure_ascii=False))
#         response.headers["Content-Type"] = "application/json; charset=utf-8"
#         return response
#
#     except Exception as e:
#         return jsonify({"error": str(e)}), 400
#
#
# #F-64 – 자연환경이 좋은 자치구 TOP 5
# @app.route("/nature-top5")
# def nature_top5():
#     try:
#         df_subset = df[["district", "green_space_per_capita"]].copy()
#         df_subset["nature_score"] = pd.to_numeric(df_subset["green_space_per_capita"], errors="coerce")
#
#         result = (
#             df_subset[["district", "nature_score"]]
#             .sort_values(by="nature_score", ascending=False)
#             .head(5)
#             .to_dict(orient="records")
#         )
#
#         response = make_response(json.dumps({
#             "title": "자연환경이 좋은 자치구 TOP 5",
#             "unit": "1인당 녹지면적",
#             "category": "nature",
#             "items": [
#                 { "rank": i + 1, "name": row["district"], "score": round(row["nature_score"], 3) }
#                 for i, row in enumerate(result)
#             ]
#         }, ensure_ascii=False))
#         response.headers["Content-Type"] = "application/json; charset=utf-8"
#         return response
#
#     except Exception as e:
#         return jsonify({"error": str(e)}), 400


#F-66 – 자치구 한 줄 소개 문장 제공
@app.route("/district-summary")
def district_summary():
    try:
        name = request.args.get("name")
        filtered = df[df["district"] == name]

        if filtered.empty:
            return jsonify({"error": f"'{name}' 자치구를 찾을 수 없습니다."}), 404

        row = filtered.iloc[0]

        # 실제 지표 컬럼으로 점수 계산
        category_columns = {
            "safety": 1 - row["crime_rate"],
            "walkenv": 1 - row[["senior_pedestrian_accidents", "steep_slope_count"]].mean(),
            "relation": row["senior_center"],
            "welfare": row[["welfare_facilities", "sports_center"]].mean(),
            "culture": row["cultural_facilities"],
            "transport": row[["subway_station_count", "bus_stop_density"]].mean(),
            "medical": row[["medical_corporations_count", "emergency_room_count"]].mean(),
            "employment": row["employ"],
            "air": 1 - row["pm2_5_level"],
            "nature": row["green_space_per_capita"]
        }

        # 실제 컬럼 매핑 (다른 구 평균 계산용)
        cat_to_cols = {
            "safety": ["crime_rate"],
            "walkenv": ["senior_pedestrian_accidents", "steep_slope_count"],
            "relation": ["senior_center"],
            "welfare": ["welfare_facilities", "sports_center"],
            "culture": ["cultural_facilities"],
            "transport": ["subway_station_count", "bus_stop_density"],
            "medical": ["medical_corporations_count", "emergency_room_count"],
            "employment": ["employ"],
            "air": ["pm2_5_level"],
            "nature": ["green_space_per_capita"]
        }

        category_labels = {
            "safety": "치안이 가장 좋은",
            "walkenv": "보행환경이 가장 좋은",
            "relation": "경로당이 가장 많은",
            "welfare": "복지시설이 가장 많은",
            "culture": "문화시설이 가장 많은",
            "transport": "대중교통이 가장 편리한",
            "medical": "의료 접근성이 가장 좋은",
            "employment": "노인 일자리가 가장 많은",
            "air": "대기환경이 가장 좋은",
            "nature": "자연환경이 가장 좋은"
        }

        max_diff = -float("inf")
        main_category = None

        for cat, val in category_columns.items():
            cols = cat_to_cols[cat]
            comp_df = df[df["district"] != name][cols].copy()

            # 반전 필요한 지표 처리
            if cat in ["safety", "walkenv", "air"]:
                comp_df = 1 - comp_df

            avg_score = comp_df.mean(axis=1).mean()
            diff = val - avg_score

            if diff > max_diff:
                max_diff = diff
                main_category = cat

        summary = f"{name}는 {category_labels[main_category]} 자치구입니다."
        # 한글로 출력되게
        summary = f"{name}는 {category_labels[main_category]} 자치구입니다."

        response = make_response(json.dumps({
            "district": name,
            "summary": summary
        }, ensure_ascii=False))  # ✅ 한글 깨짐 방지

        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response



    except Exception as e:
        return jsonify({"error": str(e)}), 400


#F-99 – 자치구별 카테고리 점수 조회 API
@app.route("/district-features")
def district_features():
    try:
        name = request.args.get("name")
        row = df[df["district"] == name]

        if row.empty:
            return jsonify({"error": f"{name} 자치구를 찾을 수 없습니다."}), 404

        row = row.iloc[0]

        features = {
            "safety": 1 - row["crime_rate"],
            "walkenv": 1 - row[["senior_pedestrian_accidents", "steep_slope_count"]].mean(),
            "relation": row["senior_center"],
            "welfare": row[["sports_center", "welfare_facilities"]].mean(),
            "culture": row["cultural_facilities"],
            "transport": row[["subway_station_count", "bus_stop_density"]].mean(),
            "medical": row[["medical_corporations_count", "emergency_room_count"]].mean(),
            "employment": row["employ"],
            "nature": row["green_space_per_capita"],
            "air": 1 - row["pm2_5_level"]
        }

        response = make_response(json.dumps({
            "district": name,
            "features": {k: round(v, 2) for k, v in features.items()}
        }, ensure_ascii=False))  # ✅ 한글 깨짐 방지

        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response


    except Exception as e:
        return jsonify({"error": str(e)}), 500

    

# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)