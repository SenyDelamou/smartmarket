-- Création de la base de données
CREATE DATABASE IF NOT EXISTS smart_market;
USE smart_market;

-- Table des utilisateurs
CREATE TABLE users (
    user_id INT PRIMARY KEY AUTO_INCREMENT,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    role ENUM('admin', 'user', 'analyst') DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Table des datasets utilisateur
CREATE TABLE user_datasets (
    dataset_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    dataset_name VARCHAR(100) NOT NULL UNIQUE,
    file_path VARCHAR(255) NOT NULL,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Table météo
CREATE TABLE meteo (
    meteo_id INT PRIMARY KEY AUTO_INCREMENT,
    date DATE NOT NULL,
    zone VARCHAR(50) NOT NULL,
    temperature DECIMAL(4,1),
    precipitation DECIMAL(5,2),
    humidite INT,
    condition_meteo VARCHAR(50),
    UNIQUE KEY unique_date_zone (date, zone)
);

-- Table des tendances Google
CREATE TABLE tendances (
    tendance_id INT PRIMARY KEY AUTO_INCREMENT,
    date DATE NOT NULL,
    mot_cle VARCHAR(100) NOT NULL,
    score_tendance INT NOT NULL,
    zone VARCHAR(50),
    categorie VARCHAR(50),
    UNIQUE KEY unique_date_keyword (date, mot_cle, zone)
);

-- Table des jours fériés
CREATE TABLE jours_feries (
    ferie_id INT PRIMARY KEY AUTO_INCREMENT,
    date DATE NOT NULL,
    nom_ferie VARCHAR(100) NOT NULL,
    type_ferie ENUM('national', 'local', 'religieux') NOT NULL,
    zone VARCHAR(50),
    description TEXT,
    UNIQUE KEY unique_date_zone (date, zone)
);

-- Table des prédictions
CREATE TABLE predictions (
    prediction_id INT PRIMARY KEY AUTO_INCREMENT,
    dataset_id INT NOT NULL,
    date_prediction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    date_cible DATE NOT NULL,
    type_prediction ENUM('ventes', 'quantite', 'benefice', 'zone_score') NOT NULL,
    valeur_predite DECIMAL(12,2) NOT NULL,
    intervalle_confiance DECIMAL(5,2),
    precision_prediction DECIMAL(5,2),
    zone VARCHAR(50),
    produit VARCHAR(100),
    FOREIGN KEY (dataset_id) REFERENCES user_datasets(dataset_id)
);

-- Index pour optimiser les requêtes
CREATE INDEX idx_ventes_date ON ventes(date_vente);
CREATE INDEX idx_ventes_produit ON ventes(produit);
CREATE INDEX idx_ventes_zone ON ventes(zone);
CREATE INDEX idx_meteo_date ON meteo(date);
CREATE INDEX idx_tendances_date ON tendances(date);
CREATE INDEX idx_predictions_date ON predictions(date_cible);

-- Vues pour faciliter les analyses
CREATE VIEW v_ventes_quotidiennes AS
SELECT 
    date_vente,
    zone,
    COUNT(*) as nb_ventes,
    SUM(quantite) as total_quantite,
    SUM(quantite * prix_unitaire) as chiffre_affaires,
    SUM(quantite * (prix_unitaire - COALESCE(cout_unitaire, 0))) as benefice
FROM ventes
GROUP BY date_vente, zone;

CREATE VIEW v_performance_produits AS
SELECT 
    v.produit,
    v.categorie,
    COUNT(DISTINCT v.date_vente) as jours_vente,
    SUM(v.quantite) as total_quantite,
    AVG(v.prix_unitaire) as prix_moyen,
    SUM(v.quantite * v.prix_unitaire) as ca_total,
    SUM(v.quantite * (v.prix_unitaire - COALESCE(v.cout_unitaire, 0))) as benefice_total
FROM ventes v
GROUP BY v.produit, v.categorie;