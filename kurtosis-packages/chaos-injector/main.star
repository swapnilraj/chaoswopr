"""Chaos Injector Package for chaoswopr.

Deploys chaos injection containers with NET_ADMIN capability for tc/netem fault injection.
Can be used standalone or alongside an Ethereum testnet deployment.
"""


def run(plan, args=None):
    """Deploy chaos injection services with NET_ADMIN capability.

    Args:
        plan: Kurtosis plan object
        args: Configuration arguments with:
            - num_injectors (int): Number of chaos injector containers (default: 3)
            - target_services (list): Names of services to inject faults into
            - network_faults (dict): Network fault configuration (latency, loss, etc.)

    Returns:
        Dictionary with deployment info
    """
    if args == None:
        args = {}

    num_injectors = args.get("num_injectors", 3)
    target_services = args.get("target_services", [])

    injector_services = []

    for i in range(num_injectors):
        service_name = "chaos-injector-{}".format(i + 1)

        # Deploy chaos injector with NET_ADMIN capability
        plan.add_service(
            name=service_name,
            config=ServiceConfig(
                image="alpine:latest",
                cmd=[
                    "/bin/sh",
                    "-c",
                    "apk add --no-cache iproute2-tc && sleep 3600"
                ],
                capabilities=["NET_ADMIN"],  # Enable tc/netem for network fault injection
            )
        )

        injector_services.append(service_name)

    plan.print("Deployed {} chaos injectors with NET_ADMIN capability".format(num_injectors))

    # Return deployment info
    return {
        "injector_services": injector_services,
        "num_injectors": num_injectors,
        "capabilities": ["NET_ADMIN"],
    }
