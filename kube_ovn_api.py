from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from kubernetes import client, config, watch
from pydantic import BaseModel
from typing import Dict, Any, Optional
import asyncio



app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (change this in production)
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)


# Load kubeconfig (or use in-cluster configuration)
config.load_kube_config()  # Use config.load_incluster_config() if running inside a pod
api = client.CustomObjectsApi()

NAMESPACE = "kube-system"
GROUP = "kubeovn.io"
VERSION = "v1"

RESOURCES: tuple[list[str]] = ["vpcs", "subnets", "ippools", "ips", "iptables-dnat-rules", "iptables-eips", "iptables-fip-rules", "iptables-snat-rules", "ovn-dnat-rules", "ovn-eips", "ovn-fips", "ovn-snat-rules", "provider-networks", "qos-policies", "security-groups", "switch-lb-rules", "vips", "vlans", "vpc-dnses", "vpc-nat-gateways"]
NAMESPACED_RESOURCES: tuple[list[str]] = []


class PatchBody(BaseModel):
    spec: Dict[str, Any]


class CreateBody(BaseModel):
    name: str
    namespace: Optional[str] = None
    spec: Dict[str, Any]


@app.get("/api/{resource}")
async def get_resources(resource: str):
    if resource not in RESOURCES:
        return {"error": "Invalid resource type"}
    try:
        result = api.list_cluster_custom_object(GROUP, VERSION, resource)
        return result["items"]
    except Exception as e:
        return {"error": str(e)}
    

@app.post("/api/{resource}")
async def create_resource(resource: str, create_body: CreateBody):
    """Create a new resource with full specification"""
    if resource not in RESOURCES:
        raise HTTPException(status_code=400, detail="Invalid resource type")
    
    # Determine the correct Kind name (handle plural to singular and special cases)
    kind_mapping = {
        "vpcs": "Vpc",
        "subnets": "Subnet",
        "ippools": "IpPool",
        "ips": "IP",
        "iptables-dnat-rules": "IptablesDnatRule",
        "iptables-eips": "IptablesEIP",
        "iptables-fip-rules": "IptablesFIPRule",
        "iptables-snat-rules": "IptablesSnatRule",
        "ovn-dnat-rules": "OvnDnatRule",
        "ovn-eips": "OvnEip",
        "ovn-fips": "OvnFip",
        "ovn-snat-rules": "OvnSnatRule",
        "provider-networks": "ProviderNetwork",
        "qos-policies": "QoSPolicy",
        "security-groups": "SecurityGroup",
        "switch-lb-rules": "SwitchLBRule",
        "vips": "Vip",
        "vlans": "Vlan",
        "vpc-dnses": "VpcDns",
        "vpc-nat-gateways": "VpcNatGateway"
    }
    
    kind = kind_mapping.get(resource, resource.capitalize())
    
    manifest = {
        "apiVersion": f"{GROUP}/{VERSION}",
        "kind": kind,
        "metadata": {"name": create_body.name},
        "spec": create_body.spec
    }
    
    # Add namespace if provided
    if create_body.namespace:
        manifest["metadata"]["namespace"] = create_body.namespace
    
    try:
        response = api.create_cluster_custom_object(GROUP, VERSION, resource, manifest)
        return response
    except client.rest.ApiException as e:
        if e.status == 409:
            raise HTTPException(status_code=409, detail=f"{kind} '{create_body.name}' already exists")
        raise HTTPException(status_code=e.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/subnets/{subnet_name}")
async def patch_subnet(subnet_name: str, patch_body: PatchBody):
    """Update a subnet's specifications"""
    try:
        # Get the current subnet
        current = api.get_cluster_custom_object(
            GROUP, VERSION, "subnets", subnet_name
        )
        
        # Update the spec with provided changes
        current["spec"].update(patch_body.spec)
        
        # Apply the patch
        response = api.patch_cluster_custom_object(
            GROUP, VERSION, "subnets", subnet_name, current
        )
        return response
    except client.rest.ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail=f"Subnet '{subnet_name}' not found")
        raise HTTPException(status_code=e.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/vpc-nat-gateways/{gateway_name}")
async def patch_vpc_nat_gateway(gateway_name: str, patch_body: PatchBody):
    """Update a VPC NAT gateway's specifications"""
    try:
        # Get the current gateway
        current = api.get_cluster_custom_object(
            GROUP, VERSION, "vpc-nat-gateways", gateway_name
        )
        
        # Update the spec with provided changes
        current["spec"].update(patch_body.spec)
        
        # Apply the patch
        response = api.patch_cluster_custom_object(
            GROUP, VERSION, "vpc-nat-gateways", gateway_name, current
        )
        return response
    except client.rest.ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail=f"VPC NAT Gateway '{gateway_name}' not found")
        raise HTTPException(status_code=e.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/subnets/{subnet_name}")
async def delete_subnet(subnet_name: str):
    """Delete a subnet"""
    try:
        # Check if subnet exists first
        api.get_cluster_custom_object(GROUP, VERSION, "subnets", subnet_name)
        
        # Delete the subnet
        response = api.delete_cluster_custom_object(
            GROUP, VERSION, "subnets", subnet_name
        )
        return {"message": f"Subnet '{subnet_name}' deleted successfully"}
    except client.rest.ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail=f"Subnet '{subnet_name}' not found")
        raise HTTPException(status_code=e.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/vpc-nat-gateways/{gateway_name}")
async def delete_vpc_nat_gateway(gateway_name: str):
    """Delete a VPC NAT gateway"""
    try:
        # Check if gateway exists first
        api.get_cluster_custom_object(GROUP, VERSION, "vpc-nat-gateways", gateway_name)
        
        # Delete the gateway
        response = api.delete_cluster_custom_object(
            GROUP, VERSION, "vpc-nat-gateways", gateway_name
        )
        return {"message": f"VPC NAT Gateway '{gateway_name}' deleted successfully"}
    except client.rest.ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail=f"VPC NAT Gateway '{gateway_name}' not found")
        raise HTTPException(status_code=e.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/{resource}/{resource_name}")
async def patch_resource(resource: str, resource_name: str, patch_body: PatchBody):
    """Update any resource's specifications"""
    if resource not in RESOURCES:
        raise HTTPException(status_code=400, detail="Invalid resource type")
    
    try:
        # Get the current resource
        current = api.get_cluster_custom_object(
            GROUP, VERSION, resource, resource_name
        )
        
        # Update the spec with provided changes
        current["spec"].update(patch_body.spec)
        
        # Apply the patch
        response = api.patch_cluster_custom_object(
            GROUP, VERSION, resource, resource_name, current
        )
        return response
    except client.rest.ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail=f"{resource.capitalize()} '{resource_name}' not found")
        raise HTTPException(status_code=e.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/{resource}/{resource_name}")
async def delete_resource(resource: str, resource_name: str):
    """Delete any resource"""
    if resource not in RESOURCES:
        raise HTTPException(status_code=400, detail="Invalid resource type")
    
    try:
        # Check if resource exists first
        api.get_cluster_custom_object(GROUP, VERSION, resource, resource_name)
        
        # Delete the resource
        response = api.delete_cluster_custom_object(
            GROUP, VERSION, resource, resource_name
        )
        return {"message": f"{resource.capitalize()} '{resource_name}' deleted successfully"}
    except client.rest.ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail=f"{resource.capitalize()} '{resource_name}' not found")
        raise HTTPException(status_code=e.status, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    w = watch.Watch()
    try:
        for resource in RESOURCES:
            for event in w.stream(api.list_cluster_custom_object, GROUP, VERSION, resource):
                await websocket.send_json({"resource": resource, "type": event["type"], "object": event["object"]})
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        w.stop()
