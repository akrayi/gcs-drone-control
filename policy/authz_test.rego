package gcs.authz_test

import rego.v1
import data.gcs.authz.allow

test_role_matrix if {
    every role in ["admin", "pilot", "viewer", "unknown"] {
        every action in ["READ", "TAKEOFF", "MOVE", "LAND", "RETURN_HOME", "CLEAR_SAFETY", "USERS_READ", "USERS_WRITE", "DELETE"] {
            actual := allow with input as {"resource": "shared-drone", "subject": {"role": role, "active": true}, "action": action}
            expected := permitted(role, action)
            actual == expected
        }
    }
}

permitted(role, action) := true if {
    role in {"admin", "pilot", "viewer"}
    action == "READ"
} else := true if {
    role in {"admin", "pilot"}
    action in {"TAKEOFF", "MOVE", "LAND", "RETURN_HOME"}
} else := true if {
    role == "admin"
    action in {"CLEAR_SAFETY", "USERS_READ", "USERS_WRITE"}
} else := false

test_inactive_denied if {
    not allow with input as {"resource": "shared-drone", "subject": {"role": "admin", "active": false}, "action": "TAKEOFF"}
}

test_missing_input_denied if {
    not allow with input as {}
}

test_other_resource_denied if {
    not allow with input as {"resource": "other", "subject": {"role": "admin", "active": true}, "action": "READ"}
}
