def run(plan, args={}):
    """Test Kurtosis NET_ADMIN capability support"""

    # Add a service with NET_ADMIN capability
    plan.add_service(
        name = "test-net-admin",
        config = ServiceConfig(
            image = "alpine:latest",
            cmd = ["/bin/sh", "-c", "apk add --no-cache iproute2 && sleep 3600"],
            docker_config = {
                "CapAdd": ["NET_ADMIN"]
            }
        )
    )

    # Wait for iproute2 to install
    plan.exec(
        service_name = "test-net-admin",
        recipe = ExecRecipe(
            command = ["/bin/sh", "-c", "while ! which tc > /dev/null 2>&1; do sleep 1; done; echo 'iproute2 ready'"]
        )
    )

    plan.print("NET_ADMIN test service deployed. Use 'kurtosis service exec' to verify capabilities.")
