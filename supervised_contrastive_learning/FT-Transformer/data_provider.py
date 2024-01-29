import os
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import MinMaxScaler, RobustScaler
from sklearn.model_selection import train_test_split, StratifiedKFold
import warnings
from tqdm import tqdm
import random
from sklearn.utils import resample
import time
import gc

warnings.filterwarnings('ignore')

def filter_classes_with_condition(df):
    filtered_df = df[df['classes'].isin([0, 1, 3])]
    return filtered_df

def deterioration_filter_stay_ids(group):
    
    if all(group.head(3)['Annotation'] == 'no_circ'):
        if all(group.tail(10)['classes'] == 3):
            return True
    return False

def recovery_filter_stay_ids(group):
    # 처음 3개 관측치의 Annotation이 모두 'no_circ'인 경우만 고려
    if all(group.head(3)['Annotation'] == 'no_circ'):
        # 'classes'가 2인 마지막 관측치 찾기
        last_class_2_index = group[group['classes'] == 2].index.max()
        if pd.notna(last_class_2_index):
            # 해당 인덱스까지의 데이터 반환
            return group.loc[:last_class_2_index]
    return pd.DataFrame()

def visual_df(df, mode):
    
    if mode == 'mimic':
        patient_id = 'subject_id'
        stay_id = 'stay_id'

    else:
        patient_id = 'uniquepid'
        stay_id = 'patientunitstayid'

    recovery_situation = {0, 1, 2, 3}
    deterioration_situation = {0, 1, 3}

        
    recover_state = df[df['classes'].isin(recovery_situation)].groupby(stay_id)['classes'].nunique()
    recover_state = recover_state[recover_state == len(recovery_situation)].index

    recover_set = df[df[stay_id].isin(recover_state)]

    deterioration_state = df[df['classes'].isin(deterioration_situation)].groupby(stay_id)['classes'].nunique()
    deterioration_state = deterioration_state[deterioration_state == len(deterioration_situation)].index

    deterioration_set = df[df[stay_id].isin(deterioration_state)]


    deterioration_set = filter_classes_with_condition(deterioration_set)

    deterioration_grouped = deterioration_set.groupby(stay_id)

    # 조건을 만족하는 stay_id 필터링
    valid_stay_ids = [name for name, group in deterioration_grouped if deterioration_filter_stay_ids(group)]
    deterioration_df = deterioration_set[deterioration_set[stay_id].isin(valid_stay_ids)].copy()

    recover_grouped = recover_set.groupby(stay_id)
    
     # 조건을 만족하는 데이터 필터링
    recovery_df = pd.concat([recovery_filter_stay_ids(group) for _, group in recover_grouped])
    
    total_dataset = pd.concat([recovery_df, deterioration_df])
    
    return total_dataset.reset_index(drop=True)



   

def check_class_ratio(dataset):
    class_ratio = round(np.mean(dataset.classes), 4)
    return class_ratio

def data_split(df, seed, train_ratio, Threshold, n_trial, mode):
    
    if mode == 'mimic':
        patient_id = 'subject_id'
        stay_id = 'stay_id'
        seed = seed
    else:
        patient_id = 'uniquepid'
        stay_id = 'patientunitstayid'
        seed = seed
        
    data = df.copy()
    gc.collect()
    
    search_time = time.time()
     
    for T in range(n_trial):
        array = data[patient_id].unique()
        
        seed = np.random.randint(0, 10000, 1)
        seed = 393
        np.random.seed(seed) 
        np.random.shuffle(array)


        split_point = int(train_ratio * len(array))
        stay_for_train, stay_for_test = np.split(array, [split_point])

        
        condition_train = data[patient_id].isin(stay_for_train)
        holdout_train = data[condition_train]

        condition_test = data[patient_id].isin(stay_for_test)
        holdout_test = data[condition_test]

        train_class_ratio  = check_class_ratio(holdout_train)
        test_class_ratio  = check_class_ratio(holdout_test)
                
        if abs(train_class_ratio - test_class_ratio) <= Threshold:
            
            break  # 클래스 비율의 차이가 threshold 이하일 경우 반복문 종료
        
        if T % 100 == 0:
            print('Trial: ', T)
            
        if T % 10000 == 0:
        
            Threshold = Threshold + 0.05
            print('Threshold 조정 + 0.05, 현재 한계값: {}'.format(Threshold))
        
        if T == 9999:
            print('최대 Trial 달성, 분할 불가')
    
    train = holdout_train.copy()
    test = holdout_test.copy()
    search_time_end = time.time()
    
    trn_class1 = train.classes.value_counts()[0]
    trn_class2 = train.classes.value_counts()[1]
    trn_class3 = train.classes.value_counts()[2]
    trn_class4 = train.classes.value_counts()[3]
    
    tes_class1 = test.classes.value_counts()[0]
    tes_class2 = test.classes.value_counts()[1]
    tes_class3 = test.classes.value_counts()[2]
    tes_class4 = test.classes.value_counts()[3]
    
    
    print("========== 데이터셋 분할 정보 ==========")
    print("데이터셋 비율: 학습 = {:.2f}, 테스트 = {:.2f}".format(train_ratio, 1-train_ratio))
    print("학습셋 클래스 비율: {}".format(train.classes.value_counts().sort_index()))
    print("테스트셋 클래스 비율: {}".format(test.classes.value_counts().sort_index()))
    print("--------------------------------------")

    print("========== 클래스 비율 ==========")
    print("학습셋 클래스 비율: {:.2f}:{:.2f}:{:.2f}:{:.2f}".format(
        trn_class1/(trn_class1+trn_class2+trn_class3+trn_class4),
        trn_class2/(trn_class1+trn_class2+trn_class3+trn_class4),
        trn_class3/(trn_class1+trn_class2+trn_class3+trn_class4),
        trn_class4/(trn_class1+trn_class2+trn_class3+trn_class4)))
    print("테스트셋 클래스 비율: {:.2f}:{:.2f}:{:.2f}:{:.2f}".format(
        tes_class1/(tes_class1+tes_class2+tes_class3+tes_class4),
        tes_class2/(tes_class1+tes_class2+tes_class3+tes_class4),
        tes_class3/(tes_class1+tes_class2+tes_class3+tes_class4),
        tes_class4/(tes_class1+tes_class2+tes_class3+tes_class4)))
    print("--------------------------------------")

    print("========== 환자 및 체류 정보 ==========")
    print("학습셋 환자 수: {}".format(len(train[patient_id].unique())))
    print("테스트셋 환자 수: {}".format(len(test[patient_id].unique())))
    print("학습셋 체류 수: {}".format(len(train[stay_id].unique())))
    print("테스트셋 체류 수: {}".format(len(test[stay_id].unique())))
    print("--------------------------------------")

    print("========== 실험 설정 ==========")
    print("분할 시드: {}".format(seed))
    print("학습 비율: {}".format(train_ratio))
    print("임계값: {}".format(Threshold))
    print("--------------------------------------")

    print("========== 실행 결과 ==========")
    print("총 소요 시간(초): {:.2f}".format(search_time_end - search_time))
    print("시도한 시행 횟수: {}".format(T))

    return train.reset_index(drop=True), test.reset_index(drop=True)

class TableDataset(Dataset):
    def __init__(self,data_path,data_type,mode,seed, augmentation, visualization):
        self.data_path = data_path
        self.data_type = data_type # eicu or mimic
        self.mode = mode # train / valid / test
        self.target = 'classes'
        self.seed = seed
        self.augmentation = augmentation
        self.visualization = visualization
        self.df_num, self.df_cat, self.y = self.__prepare_data__()

    def __prepare_data__(self):
        df_raw = pd.read_csv(self.data_path, compression='gzip')
        print(len(df_raw))
        df_raw.replace([np.inf, -np.inf], np.nan, inplace=True)
        df_raw.fillna(0, inplace=True)
        
        # self.num_features = ['HR', 'Temperature', 'MAP', 'ABPs', 'ABPd', 'Respiratory Rate', 'O2 Sat (%)', 'SVO2', 'SpO2',
        #                      'PaO2','FIO2 (%)', 'EtCO2', 'Cardiac Output', 'GCS_score', 'Lactate', 'Lactate_clearance_1h',
        #                      'Lactate_clearance_3h', 'Lactate_clearance_5h', 'Fluids(ml)', 'Glucose', 'cum_use_vaso','Alkaline_phosphatase','Age','Anion gap',
        #                      'BUN','Total Bilirubin', 'ALT', 'Troponin-T', 'Creatinine','RedBloodCell', 'pH', 'Hemoglobin', 'Hematocrit','classes', 'stay_id', 'hadm_id', 'Annotation', 'ethnicity']
        # self.cat_features = ['vasoactive/inotropic', 'Mechanical_circ_support', 'Shock_next_12h', 'Annotation']    
        
        self.cat_features = []
        self.num_features = []
        
        for col in df_raw.columns:
            if df_raw[col].nunique() == 2:
                self.cat_features.append(col)
            else:
                self.num_features.append(col) #height_fillna is included num_features bacause that in mimic only have value 0 -> eicu는 binary 지만 num에 포함하자
                
        scaler = MinMaxScaler()
        
        if self.visualization == True :
            
            df = visual_df(df_raw, mode = self.data_type)
            df_train, df_valid = data_split(df, self.seed, 0.7, 0.05, 1, mode = self.data_type)
            
        else:
            df_train, df_valid = data_split(df_raw, self.seed, 0.7, 0.05, 1, mode = self.data_type)
        
        if self.augmentation == True:
            
            df_class_0 = df_train[df_train['classes'] == 0]
            df_class_1 = df_train[df_train['classes'] == 1]
            df_class_2 = df_train[df_train['classes'] == 2]
            df_class_3 = df_train[df_train['classes'] == 3]

            max_size = df_class_3.shape[0]

            df_class_1_upsampled = resample(df_class_1, replace=True, n_samples=max_size, random_state=123)
            df_class_2_upsampled = resample(df_class_2, replace=True, n_samples=max_size, random_state=123)
            df_class_3_upsampled = resample(df_class_3, replace=True, n_samples=max_size, random_state=123)

            df_train = pd.concat([df_class_0, df_class_1_upsampled, df_class_2_upsampled, df_class_3_upsampled]).reset_index(drop=True)
            
            print("========== 클래스 비율 ==========")
            print("학습셋 클래스 비율", df_train.classes.value_counts().sort_index())
            
        
    
        # if dataset is eicu
        if self.data_type == 'mimic':
            if self.mode == "train":
                X_num = df_train[self.num_features].drop(['classes', 'stay_id', 'subject_id','hadm_id', 'Annotation', 'ethnicity'], axis = 1)
                X_num_scaled = scaler.fit_transform(X_num)
                
                X_num = pd.DataFrame(X_num_scaled,columns = X_num.columns)
                X_cat = df_train[self.cat_features].drop(['Shock_next_12h'], axis = 1)
                y = df_train[self.target]
                return X_num, X_cat, y
            
            else:
                X_num_standard = df_train[self.num_features].drop(['classes', 'stay_id', 'subject_id','hadm_id', 'Annotation', 'ethnicity'], axis = 1)
                scaler.fit(X_num_standard)
                
                X_num = df_valid[self.num_features].drop(['classes', 'stay_id', 'subject_id','hadm_id', 'Annotation', 'ethnicity'], axis = 1)
                X_num_scaled = scaler.transform(X_num)
                
                X_num = pd.DataFrame(X_num_scaled,columns = X_num.columns)
                X_cat = df_valid[self.cat_features].drop(['Shock_next_12h'], axis = 1)
                y = df_valid[self.target]
                return X_num, X_cat, y

        # if dataset is eicu
        else:
            ## scaler fitting을 위한 과정
            df_scaling = pd.read_csv("/Users/DAHS/Desktop/ECP_CONT/ECP_SCL/Case Labeling/eICU.csv.gz", compression='gzip')
            df_train, _ = data_split(df_scaling,self.seed, 0.7, 0.05, 1)
            X_num_standard = df_train[self.num_features].drop(['classes', 'patientunitstayid', 'uniquepid', 'Annotation', 'ethnicity'], axis = 1)
            scaler.fit(X_num_standard)

            X_num = df_raw[self.num_features].drop(['classes', 'patientunitstayid', 'uniquepid', 'Annotation', 'ethnicity'], axis = 1)
            X_num_scaled = scaler.transform(X_num)
            X_num = pd.DataFrame(X_num_scaled,columns = X_num.columns)
            X_cat = df_raw[self.cat_features].drop(['Shock_next_12h'], axis = 1)
            y = df_raw[self.target]
            return X_num, X_cat, y

    def __getitem__(self,index):
      
        X_num_features = torch.tensor(self.df_num.iloc[index,:].values,dtype=torch.float32)
        X_cat_features = torch.tensor(self.df_cat.iloc[index,:].values,dtype=torch.float32).long()
        label = torch.tensor(int(self.y.iloc[index]),dtype=torch.float32)

        return X_num_features, X_cat_features, label
    
    def __len__(self):
        return self.y.shape[0]
    

