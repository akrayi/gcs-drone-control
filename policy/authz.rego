package gcs.authz

import rego.v1

default allow := false

allow if {
    input.resource == "shared-drone"
    input.subject.active == true
    input.subject.role in {"admin", "pilot", "viewer"}
    input.action == "READ"
}

allow if {
    input.resource == "shared-drone"
    input.subject.active == true
    input.subject.role in {"admin", "pilot"}
    input.action in {"TAKEOFF", "MOVE", "LAND", "RETURN_HOME"}
}

allow if {
    input.resource == "shared-drone"
    input.subject.active == true
    input.subject.role == "admin"
    input.action in {"CLEAR_SAFETY", "USERS_READ", "USERS_WRITE"}
}
