import os
from flask import Flask, request, jsonify, make_response, render_template
import pandas as pd
import json
from flask_cors import CORS
import pymysql
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv() # 로컬에서만 자동 돌아가는 함수
# local 에서는 .env 파일 참조, cloud에서는 railway 환경변수 자동 참조
conn = pymysql.connect(
    host = os.getenv("MYSQLHOST"),
    port = int(os.getenv("MYSQLPORT")),
    user = os.getenv("MYSQLUSER"),
    password = os.getenv("MYSQLPASSWORD"),
    db = os.getenv("MYSQL_DATABASE"),
    charset = 'utf8mb4',
    cursorclass = pymysql.cursors.DictCursor
)


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
        
        #가중치 DB저장 추가 코드
        try:
            cursor = conn.cursor()
            insert_query = """
                            INSERT INTO question_weights
                            (q1,q2,q3,q4,q5,q6,q7,q8,q9,q10)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """
            questions = [f'q{i}' for i in range(1,11)]
            values = tuple(float(request.args.get(q,0)) for q in questions)
            
            cursor.execute(insert_query, values)
            conn.commit()
        except Exception as db_err:
            print('가중치 저장 실패: ', db_err)

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
        # 안전 지표 (낮을수록 좋음)
        safety_cols = ["crime_rate", "senior_pedestrian_accidents"]
        df_subset = df[["district", "latitude", "longitude"] + safety_cols].copy()
        df_subset["safety_score"] = df_subset[safety_cols].mean(axis=1)

        # 낮은 값일수록 안전하므로 오름차순 정렬
        df_sorted = df_subset.sort_values(by="safety_score", ascending=True).head(5).reset_index(drop=True)

        # 결과 구성
        result = [
            {
                "rank": i + 1,
                "name": row["district"],
                "score": round(row["safety_score"], 3),
                "latitude": row["latitude"],
                "longitude": row["longitude"]
            }
            for i, row in df_sorted.iterrows()
        ]

        response = make_response(json.dumps({
            "title": "안전한 동네 TOP 5",
            "unit": "범죄율 및 노인 보행자 사고 평균 점수",
            "category": "safety",
            "items": result
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
                { "rank": i + 1, "name": row["district"], "score": row["walk_score"],
                  "latitude": df[df["district"] == row["district"]]["latitude"].values[0],
                  "longitude": df[df["district"] == row["district"]]["longitude"].values[0]
                  }
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
                { "rank": i + 1, "name": row["district"], "score": round(row["transport_score"], 3),
                  "latitude": df[df["district"] == row["district"]]["latitude"].values[0],
                  "longitude": df[df["district"] == row["district"]]["longitude"].values[0]
                  }
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
                { "rank": i + 1, "name": row["district"], "score": round(row["medical_score"], 3),
                  "latitude": df[df["district"] == row["district"]]["latitude"].values[0],
                  "longitude": df[df["district"] == row["district"]]["longitude"].values[0]
                  }
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
                { "rank": i + 1, "name": row["district"], "score": int(row["social_score"]),
                  "latitude": df[df["district"] == row["district"]]["latitude"].values[0],
                  "longitude": df[df["district"] == row["district"]]["longitude"].values[0]
                  }
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
                { "rank": i + 1, "name": row["district"], "score": round(row["culture_score"], 3),
                  "latitude": df[df["district"] == row["district"]]["latitude"].values[0],
                  "longitude": df[df["district"] == row["district"]]["longitude"].values[0]
                  }
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
                { "rank": i + 1, "name": row["district"], "score": round(row["activity_score"], 3),
                  "latitude": df[df["district"] == row["district"]]["latitude"].values[0],
                  "longitude": df[df["district"] == row["district"]]["longitude"].values[0]
                  }
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
                { "rank": i + 1, "name": row["district"], "score": round(row["nature_score"], 3),
                  "latitude": df[df["district"] == row["district"]]["latitude"].values[0],
                  "longitude": df[df["district"] == row["district"]]["longitude"].values[0]
                  }
                for i, row in enumerate(result)
            ]
        }, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ✅ 단일 API: 다양한 상위/하위 자치구 요청 처리
from flask import request, jsonify, make_response
import json


@app.route("/district-top5")
def district_top5():
    try:
        mode = request.args.get("mode")  # 'friendly', 'unfriendly', 'category'
        category_name = request.args.get("category")

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

        category_labels = {
            "치안": "치안이 가장 좋은",
            "보행환경": "보행환경이 가장 좋은",
            "대중교통": "대중교통이 가장 편리한",
            "병원접근성": "병원 접근성이 가장 좋은",
            "노인복지시설": "복지시설이 가장 많은",
            "문화시설": "문화시설이 가장 많은",
            "경로당": "경로당이 가장 많은",
            "노인일자리": "노인 일자리가 가장 많은",
            "대기환경": "대기환경이 가장 좋은",
            "자연환경": "녹지가 가장 많은"
        }

        REVERSE_COLUMNS = ["crime_rate", "senior_pedestrian_accidents", "steep_slope_count", "pm2_5_level"]

        if mode not in ["friendly", "unfriendly", "category"]:
            return jsonify({"error": "mode 파라미터가 필요하며 'friendly', 'unfriendly', 'category' 중 하나여야 합니다."}), 400

        df_copy = df.copy()
        score_map = {}

        for cat, cols in CATEGORY_COLUMNS.items():
            vals = df_copy[cols].copy()
            if cat in ["치안", "보행환경", "대기환경"]:
                vals = 1 - vals
            score_map[cat] = vals.mean(axis=1)

        df_score = pd.DataFrame(score_map)
        df_score["district"] = df["district"]
        df_score["longitude"] = df["longitude"]
        df_score["latitude"] = df["latitude"]

        if mode == "friendly" or mode == "unfriendly":
            df_score["total_score"] = df_score[list(CATEGORY_COLUMNS.keys())].mean(axis=1)
            df_sorted = df_score.sort_values(by="total_score", ascending=(mode == "unfriendly")).head(5).reset_index(
                drop=True)
        elif mode == "category":
            if not category_name or category_name not in CATEGORY_COLUMNS:
                return jsonify({"error": "카테고리명이 필요하거나 유효하지 않습니다."}), 400
            df_score["score"] = df_score[category_name]
            df_sorted = df_score.sort_values(by="score", ascending=False).head(5).reset_index(drop=True)

        # 전체 평균 계산
        avg_scores = {
            cat: round(df_score[cat].mean(), 3)
            for cat in CATEGORY_COLUMNS
        }

        # 결과 포맷 구성
        result = []
        for i, row in df_sorted.iterrows():
            if mode == "category":
                metric_data = [{
                    "name": category_name,
                    "selectedDistrict": round(row[category_name], 3),
                    "average": avg_scores[category_name]
                }]
            else:
                metric_data = [
                    {
                        "name": cat,
                        "selectedDistrict": round(row[cat], 3),
                        "average": avg_scores[cat]
                    } for cat in CATEGORY_COLUMNS
                ]

            # info 문구
            if mode == "friendly" or mode == "unfriendly":
                max_diff = -float("inf") if mode == "friendly" else float("inf")
                target_cat = None
                for cat in CATEGORY_COLUMNS:
                    diff = row[cat] - avg_scores[cat]
                    if (mode == "friendly" and diff > max_diff) or (mode == "unfriendly" and diff < max_diff):
                        max_diff = diff
                        target_cat = cat
                label = category_labels.get(target_cat, "")
                info = f"{row['district']}는 {label} 동네입니다."
            else:
                info = None

            entry = {
                "district": row["district"],
                "rank": i + 1,
                "longitude": row["longitude"],
                "latitude": row["latitude"],
                "metricData": metric_data
            }
            if info:
                entry["info"] = info

            result.append(entry)

        response = make_response(json.dumps({"data": result}, ensure_ascii=False))
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    
# F-67 가장 많이 1위로 나온 TOP3 자치구 각각 몇 번 나왔는지까지. 
@app.route("/top3-district", methods = ['GET'])
def get_top_district():
    try:
        cursor = conn.cursor()
        query = """
                SELECT top1 AS district, COUNT(*) AS count
                FROM district_ranking 
                GROUP BY top1
                ORDER BY COUNT(*) DESC
                LIMIT 3;
                """
        cursor.execute(query)
        result = cursor.fetchall()     
        return jsonify({"district" : []})
    
    except Exception as e:
        return jsonify({'error' : str(e)}), 500
    
    finally:
        cursor.close()

# F-68 가장 높은 점수를 받은 컬럼 top 5 즉 질문 카테고리
@app.route('/top5-categories', methods = ['GET'])
def get_top5_categories():
    try:
        cursor = conn.cursor()
        query = """
                SELECT 
                AVG(q1) AS q1,AVG(q2) AS q2,AVG(q3) AS q3,
                AVG(q4) AS q4,AVG(q5) AS q5,AVG(q6) AS q6,
                AVG(q7) AS q7,AVG(q8) AS q8,AVG(q9) AS q9,
                AVG(q10) AS q10
                FROM question_weights
                """
        cursor.execute(query)
        row = cursor.fetchone()

        q_to_category = {
        'q1': '안전',
        'q2': '보행환경',
        'q3': '자연',
        'q4': '복지',
        'q5': '문화',
        'q6': '관계',
        'q7': '대중교통',
        'q8': '사회참여',
        'q9': '의료',
        'q10': '대기환경'
    }
        category_scores = defaultdict(float)
        for question, score in row.items():
            category = q_to_category.get(question)
            if category and score is not None:
                category_scores[category] += score
        if not category_scores:
            return jsonify({"top_categories" : []})
        
        top5 = sorted(category_scores.items(), key = lambda x: x[1], reverse=True)[:5]
        result = [{'category' : k, 'score' : round(v,2)} for k, v in top5]

        return jsonify({'top_categories' : result})
    
    except Exception as e:
        return jsonify({'error' : str(e)}), 500
    
    finally:
        cursor.close()








        



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


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5050)))
