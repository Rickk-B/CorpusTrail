ALTER TABLE relevance_benchmark_adjudications
    ADD COLUMN review_packet_sha256 TEXT REFERENCES raw_artifacts(sha256);

ALTER TABLE relevance_benchmark_adjudications
    ADD COLUMN review_packet_path TEXT;

ALTER TABLE relevance_benchmark_adjudication_labels
    ADD COLUMN evidence_representation TEXT CHECK (
        evidence_representation IS NULL OR evidence_representation IN (
            'metadata', 'abstract', 'structured_text', 'pdf_text',
            'ocr_text', 'image_only'
        )
    );

ALTER TABLE relevance_benchmark_adjudication_labels
    ADD COLUMN artifact_validity TEXT CHECK (
        artifact_validity IS NULL OR artifact_validity IN (
            'verified', 'pending', 'identity_rejected', 'unreadable'
        )
    );

ALTER TABLE relevance_benchmark_adjudication_labels
    ADD COLUMN review_extent TEXT CHECK (
        review_extent IS NULL OR review_extent IN (
            'metadata', 'abstract', 'passages', 'sections', 'full_document'
        )
    );

ALTER TABLE relevance_benchmark_adjudication_labels
    ADD COLUMN evidence_sufficiency TEXT CHECK (
        evidence_sufficiency IS NULL OR evidence_sufficiency = 'sufficient'
    );

ALTER TABLE relevance_benchmark_adjudication_labels
    ADD COLUMN evaluation_partition TEXT CHECK (
        evaluation_partition IS NULL OR evaluation_partition IN (
            'development', 'evaluation', 'prospective_holdout'
        )
    );
