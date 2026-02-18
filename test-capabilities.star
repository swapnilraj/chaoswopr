def run(plan):
    # Test the new capabilities parameter
    plan.add_service(
        name = "chaos-test",
        config = ServiceConfig(
            image = "alpine:latest",
            cmd = ["/bin/sh", "-c", "apk add --no-cache iproute2 && sleep 3600"],
            capabilities = ["NET_ADMIN"]
        )
    )
