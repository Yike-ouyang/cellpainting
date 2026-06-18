#!/usr/bin/env nextflow

/*
 * Convert wide feature-extraction manifests into the tall CSV samplesheet
 * expected by the nf-core/cellpainting pipeline.
 *
 * Example:
 *   nextflow run convert_manifest.nf \
 *     --input /path/to/01_manifest \
 *     --out samplesheet.csv
 */

nextflow.enable.dsl = 2

params.input = null
params.out = "samplesheet.csv"
params.source = null
params.channel_map = [
    DNA: 1,
    RNA: 2,
    AGP: 3,
    ER: 4,
    Mito: 5,
    Brightfield: 6,
]

process CONVERT_MANIFEST {
    tag { manifest_dir.simpleName }
    publishDir { output_dir }, mode: 'copy'

    input:
    path manifest_dir
    val output_name
    val output_dir
    val source
    val channel_map_json
    path convert_script

    output:
    path output_name

    script:
    def source_arg = source ? "--source '${source}'" : ""
    """
    python3 "${convert_script}" \\
        --manifest-dir "${manifest_dir}" \\
        --out "${output_name}" \\
        --channel-map '${channel_map_json}' \\
        ${source_arg}
    """
}

workflow {
    if (!params.input) {
        error "Missing required parameter: --input <feature_extraction_manifest_dir>"
    }

    def channel_map_json = groovy.json.JsonOutput.toJson(params.channel_map)
    def out_path = file(params.out)

    CONVERT_MANIFEST(
        file(params.input, checkIfExists: true),
        out_path.name,
        out_path.parent ?: ".",
        params.source,
        channel_map_json,
        file("${projectDir}/modules/convert_manifest.py", checkIfExists: true)
    )

    CONVERT_MANIFEST.out.view { "Converted samplesheet: ${it}" }
}
