import os

from flask import Flask, request, jsonify, make_response, render_template
import pandas as pd
import json
from flask_cors import CORS


app = Flask(__name__)
CORS(app)

# 데이터 로딩

df = pd.read_csv('final_df.csv', encoding='utf-8')  # 자치구별 노인친화 지표
#df = df.iloc[2:].reset_index(drop=True)  # 데이터 시작 행 정리
df["자치구"] = df["district"]  # 자치구 이름 정리

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
        # 안전과 관련된 지표: 낮을수록 좋은 것들
        safety_cols = ["crime_rate", "senior_pedestrian_accidents"]

        # 정규화된 값이므로 평균 계산
        df_subset = df[["district"] + safety_cols].copy()
        df_subset["safety_score"] = df_subset[safety_cols].mean(axis=1)

        # 낮은 순서로 정렬 → 안전한 구
        result = (
            df_subset[["district", "safety_score"]]
            .sort_values(by="safety_score", ascending=True)
            .head(5)
            .to_dict(orient="records")
        )

        response = make_response(json.dumps({"result": result}, ensure_ascii=False))
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
        inverted_cols = ["crime_rate", "senior_pedestrian_accidents", "steep_slope_count", "pm2.5_level"]
        df_copy = df.copy()

        for col in inverted_cols:
            if col in df_copy.columns:
                df_copy[col] = 1 - pd.to_numeric(df_copy[col], errors="coerce")

        feature_cols = [col for col in df_copy.columns if col != "district"]
        df_copy[feature_cols] = df_copy[feature_cols].apply(pd.to_numeric, errors="coerce")  # ⬅ 핵심 코드

        df_copy["overall_score"] = df_copy[feature_cols].mean(axis=1)

        result = (
            df_copy[["district", "overall_score"]]
            .sort_values(by="overall_score", ascending=False)
            .head(5)
            .to_dict(orient="records")
        )

        response = make_response(json.dumps({
            "title": "고령친화 자치구 TOP 5",
            "unit": "전체 지표 평균 점수 (안전/보행은 낮을수록 가중)",
            "category": "overall",
            "items": [
                { "rank": i + 1, "name": row["district"], "score": round(row["overall_score"], 3) }
                for i, row in enumerate(result)
            ]
        }, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 400

#F-11 – 고령 비친화 자치구 하위 5개
@app.route("/senior-unfriendly-bottom5")
def senior_unfriendly_bottom5():
    try:
        inverted_cols = ["crime_rate", "senior_pedestrian_accidents", "steep_slope_count", "pm2_5_level"]
        df_copy = df.copy()

        for col in inverted_cols:
            if col in df_copy.columns:
                df_copy[col] = 1 - pd.to_numeric(df_copy[col], errors="coerce")

        feature_cols = [col for col in df_copy.columns if col != "district"]
        df_copy[feature_cols] = df_copy[feature_cols].apply(pd.to_numeric, errors="coerce")
        df_copy["overall_score"] = df_copy[feature_cols].mean(axis=1)

        result = (
            df_copy[["district", "overall_score"]]
            .sort_values(by="overall_score", ascending=True)  # 하위 5개!
            .head(5)
            .to_dict(orient="records")
        )

        response = make_response(json.dumps({
            "title": "고령 비친화 자치구 하위 5개",
            "unit": "전체 지표 평균 점수 (낮을수록 친화도 낮음)",
            "category": "overall",
            "items": [
                { "rank": i + 1, "name": row["district"], "score": round(row["overall_score"], 3) }
                for i, row in enumerate(result)
            ]
        }, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 400


#F-12 – 치안이 좋은 자치구 TOP 5
@app.route("/safety-top5")
def safety_top5():
    try:
        df_subset = df[["district", "crime_rate"]].copy()
        df_subset["safety_score"] = 1 - pd.to_numeric(df_subset["crime_rate"], errors="coerce")

        result = (
            df_subset[["district", "safety_score"]]
            .sort_values(by="safety_score", ascending=False)
            .head(5)
            .to_dict(orient="records")
        )

        response = make_response(json.dumps({
            "title": "치안이 좋은 자치구 TOP 5",
            "unit": "범죄율 (낮을수록 치안이 좋음)",
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

#F-13 – 보행환경이 좋은 자치구 TOP 5
@app.route("/walkenv-top5")
def walkenv_top5():
    try:
        cols = ["senior_pedestrian_accidents", "steep_slope_count"]
        df_subset = df[["district"] + cols].copy()
        for col in cols:
            df_subset[col] = 1 - pd.to_numeric(df_subset[col], errors="coerce")

        df_subset["walkenv_score"] = df_subset[cols].mean(axis=1)

        result = (
            df_subset[["district", "walkenv_score"]]
            .sort_values(by="walkenv_score", ascending=False)
            .head(5)
            .to_dict(orient="records")
        )

        response = make_response(json.dumps({
            "title": "보행환경이 좋은 자치구 TOP 5",
            "unit": "보행자 사고/급경사지 (낮을수록 좋음)",
            "category": "walkenv",
            "items": [
                { "rank": i + 1, "name": row["district"], "score": round(row["walkenv_score"], 3) }
                for i, row in enumerate(result)
            ]
        }, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 400



if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))