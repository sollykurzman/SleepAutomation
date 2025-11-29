#!/usr/bin/python3

import pandas as pd
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns
import joblib
import os

PATH = "ML/"

def train_inbed(df, path, evaluate=True, plot_cm=False):

    df = df.dropna().copy()

    sleep_map = {
        'Core Sleep': 'inBed',
        'Deep Sleep': 'inBed',
        'REM Sleep': 'inBed',
        'Asleep': 'inBed',
        'Awake': 'inBed',
        'notInBed': 'notInBed'
    }

    df['binary_state'] = df['sleep_state'].map(sleep_map)

    df = df.dropna(subset=['binary_state'])

    features = [
        'variance',
        'entropy',
        'power',
        'rolling_variance',
        'rolling_power'
    ]
    target = 'binary_state'

    X = df[features]
    y = df[target]

    le = LabelEncoder()
    y_encoded = le.fit_transform(y)

    class_names = le.classes_

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_encoded, 
        test_size=0.2, 
        random_state=42, 
        stratify=y_encoded
    )

    model = RandomForestClassifier(
        n_estimators=100, 
        random_state=42, 
        n_jobs=-1,
        verbose=0
    )

    model.fit(X_train, y_train)

    model_filename = path + 'in_bed_model.joblib'
    encoder_filename = path + 'in_bed_encoder.joblib'

    joblib.dump(model, path + "temp_model.joblib")
    joblib.dump(le, path + "temp_encoder.joblib")

    os.replace(path + "temp_model.joblib", model_filename)
    os.replace(path + "temp_encoder.joblib", encoder_filename)

    #Evaluation:
    y_pred = model.predict(X_test)

    accuracy = accuracy_score(y_test, y_pred)

    if evaluate:
        print(f"\nOverall Accuracy: {accuracy * 100:.2f}%")

        print("\nClassification Report:")
        print(classification_report(y_test, y_pred, target_names=class_names))

        print("\nFeature Importances:")
        importances = model.feature_importances_
        for feature, importance in zip(features, importances):
            print(f"  {feature}: {importance * 100:.2f}%")

    cm = confusion_matrix(y_test, y_pred)

    if plot_cm:

        plt.figure(figsize=(7, 5))
        sns.heatmap(
            cm, 
            annot=True, 
            fmt='d',    
            cmap='Blues', 
            xticklabels=class_names, 
            yticklabels=class_names
        )
        plt.title('Binary Confusion Matrix')
        plt.ylabel('Actual State')
        plt.xlabel('Predicted State')
        plt.tight_layout()
        plt.show()

    return model, accuracy, cm

def train_asleep(df, path, evaluate=True, plot_cm=False):

    df = df.dropna()

    df = df[df['sleep_state'] != 'notInBed'].copy()

    sleep_map = {
        'Core Sleep': 'Asleep',
        'Deep Sleep': 'Asleep',
        'REM Sleep': 'Asleep',
        'Asleep': 'Asleep',
        'Awake': 'Awake'
    }

    df['binary_state'] = df['sleep_state'].map(sleep_map)

    df = df.dropna(subset=['binary_state'])

    features = [
        'variance',
        'entropy',
        'power',
        'movement',
        'breathrate',
        'heartrate',
        'rolling_movement',
        'rolling_heartrate',
        'heartrate_change'
    ]
    target = 'binary_state'


    X = df[features]
    y = df[target]

    le = LabelEncoder()
    y_encoded = le.fit_transform(y)

    class_names = le.classes_

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_encoded, 
        test_size=0.2, 
        random_state=42, 
        stratify=y_encoded
    )

    model = RandomForestClassifier(
        n_estimators=100, 
        random_state=42, 
        n_jobs=-1,
        verbose=0
    )

    model.fit(X_train, y_train)

    model_filename = path + 'asleep_model.joblib'
    encoder_filename = path + 'asleep_encoder.joblib'

    joblib.dump(model, path + "temp_model.joblib")
    joblib.dump(le, path + "temp_encoder.joblib")

    os.replace(path + "temp_model.joblib", model_filename)
    os.replace(path + "temp_encoder.joblib", encoder_filename)

    #Evaluation:
    y_pred = model.predict(X_test)

    accuracy = accuracy_score(y_test, y_pred)

    if evaluate:
        print(f"\nOverall Accuracy: {accuracy * 100:.2f}%")

        print("\nClassification Report:")
        print(classification_report(y_test, y_pred, target_names=class_names))

        print("\nFeature Importances:")
        importances = model.feature_importances_
        for feature, importance in zip(features, importances):
            print(f"  {feature}: {importance * 100:.2f}%")

    cm = confusion_matrix(y_test, y_pred)

    if plot_cm:
        plt.figure(figsize=(7, 5))
        sns.heatmap(
            cm, 
            annot=True, 
            fmt='d',    
            cmap='Blues', 
            xticklabels=class_names, 
            yticklabels=class_names
        )
        plt.title('Binary Confusion Matrix')
        plt.ylabel('Actual State')
        plt.xlabel('Predicted State')
        plt.tight_layout()
        plt.show()

    return model, accuracy, cm

def train_state(df, path, evaluate=True, plot_cm=False):

    df = df.dropna()

    df = df[(df['sleep_state'] != 'notInBed') & (df['sleep_state'] != 'Awake') & (df['sleep_state'] != 'Asleep')].copy()

    df = df.dropna(subset=['sleep_state'])

    features = [
        'variance',
        'entropy',
        'power',
        'movement',
        'breathrate',
        'heartrate',
        'heart_coherence',
        'breath_coherence',
        'rolling_variance',
        'rolling_heartrate',
        'rolling_entropy',
        'heartrate_change'
    ]
    target = 'sleep_state'

    X = df[features]
    y = df[target]

    le = LabelEncoder()
    y_encoded = le.fit_transform(y)

    class_names = le.classes_

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_encoded, 
        test_size=0.2, 
        random_state=42, 
        stratify=y_encoded
    )

    model = RandomForestClassifier(
        n_estimators=100, 
        random_state=42, 
        n_jobs=-1,
        verbose=0
    )

    model.fit(X_train, y_train)

    model_filename = path + 'state_model.joblib'
    encoder_filename = path + 'state_encoder.joblib'

    joblib.dump(model, path + "temp_model.joblib")
    joblib.dump(le, path + "temp_encoder.joblib")

    os.replace(path + "temp_model.joblib", model_filename)
    os.replace(path + "temp_encoder.joblib", encoder_filename)

    #Evaluation:
    y_pred = model.predict(X_test)

    accuracy = accuracy_score(y_test, y_pred)

    if evaluate:
        print(f"\nOverall Accuracy: {accuracy * 100:.2f}%")

        print("\nClassification Report:")
        print(classification_report(y_test, y_pred, target_names=class_names))

        print("\nFeature Importances:")
        importances = model.feature_importances_
        for feature, importance in zip(features, importances):
            print(f"  {feature}: {importance * 100:.2f}%")

    cm = confusion_matrix(y_test, y_pred)

    if plot_cm:
        
        plt.figure(figsize=(7, 5))
        sns.heatmap(
            cm, 
            annot=True, 
            fmt='d',    
            cmap='Blues', 
            xticklabels=class_names, 
            yticklabels=class_names
        )
        plt.title('Ternary Confusion Matrix')
        plt.ylabel('Actual State')
        plt.xlabel('Predicted State')
        plt.tight_layout()
        plt.show()

    return model, accuracy, cm

df_default = pd.read_csv('Data/all_nights_formatted_data.csv')

def train_all_models(df=df_default, path=PATH):
    
    IBmodel, IBaccuracy, IBcm = train_inbed(df, path)
    ASmodel, ASaccuracy, AScm = train_asleep(df, path)
    STmodel, STaccuracy, STcm = train_state(df, path)

    print(f"\nIn-Bed Model Accuracy: {IBaccuracy * 100:.2f}%")
    print(f"Asleep Model Accuracy: {ASaccuracy * 100:.2f}%")
    print(f"State Model Accuracy: {STaccuracy * 100:.2f}%")

if __name__ == "__main__":
    train_all_models()