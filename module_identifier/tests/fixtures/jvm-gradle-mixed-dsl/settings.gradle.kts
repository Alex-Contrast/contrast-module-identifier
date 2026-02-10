rootProject.name = "mixed-dsl-platform"

include("services:rest-api", "services:batch-job")
include("libs:shared")

findProject(":services:rest-api")?.name = "api"
