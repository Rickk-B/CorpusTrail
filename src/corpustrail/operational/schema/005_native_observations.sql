ALTER TABLE search_imports
    ADD COLUMN observations_artifact_sha256 TEXT
    REFERENCES raw_artifacts(sha256);

CREATE INDEX search_imports_by_observations_artifact
    ON search_imports(observations_artifact_sha256);
