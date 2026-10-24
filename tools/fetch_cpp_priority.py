"""Fetch a priority list of C++ API classes directly, bypassing the BFS order.

The breadth-first crawler reaches thousands of plugin classes before the core
engine types, so the classes people actually ask about (AActor, UObject,
UCharacterMovementComponent, ...) can be missing for hours. This script pulls a
curated priority list first.

Usage:  python fetch_cpp_priority.py --base <dir>
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from mdconv import html_to_text
from dbpaths import base_from_argv, paths as kb_paths, ensure as kb_ensure
from crawl_cppapi import fetch_html, safe  # reuse the Cloudflare-aware fetch

KB_BASE = base_from_argv(sys.argv[1:])
_P = kb_paths(KB_BASE)
kb_ensure(_P)
RAW = _P["raw"]
OUT = os.path.join(RAW, "cppapi")
INDEX = os.path.join(RAW, "cppapi-index.json")
BASE_DOC = "https://dev.epicgames.com/documentation"
ROOT = "en-us/unreal-engine"

# Core engine types an Unreal developer asks about first. Paths are the API tree
# paths (Module/Submodule/Class), not include paths.
PRIORITY = [
    # Core / object model
    "Runtime/CoreUObject/UObject",
    "Runtime/CoreUObject/UClass",
    "Runtime/CoreUObject/UStruct",
    "Runtime/CoreUObject/UEnum",
    "Runtime/CoreUObject/UFunction",
    "Runtime/CoreUObject/UProperty",
    "Runtime/CoreUObject/FSoftObjectPtr",
    "Runtime/Core/TWeakObjectPtr",
    "Runtime/Core/TSoftObjectPtr",
    # Math / core value types
    # Engine value types that DO live under Runtime/Engine
    "Runtime/Engine/FHitResult",
    "Runtime/Engine/FOverlapResult",
    "Runtime/Engine/FTickFunction",
    "Runtime/Engine/FVector_NetQuantize",
    "Runtime/Engine/FRepMovement",
    # Engine framework
    "Runtime/Engine/AActor",
    "Runtime/Engine/UActorComponent",
    "Runtime/Engine/USceneComponent",
    "Runtime/Engine/UPrimitiveComponent",
    "Runtime/Engine/UWorld",
    "Runtime/Engine/ULevel",
    "Runtime/Engine/APawn",
    "Runtime/Engine/ACharacter",
    "Runtime/Engine/AController",
    "Runtime/Engine/APlayerController",
    "Runtime/Engine/AGameModeBase",
    "Runtime/Engine/AGameStateBase",
    "Runtime/Engine/AHUD",
    "Runtime/Engine/APlayerState",
    "Runtime/Engine/UGameInstance",
    "Runtime/Engine/UGameplayStatics",
    "Runtime/Engine/UBlueprintFunctionLibrary",
    "Runtime/Engine/UEngine",
    "Runtime/Engine/UGameViewportClient",
    # Movement / input
    "Runtime/Engine/UCharacterMovementComponent",
    "Runtime/Engine/UPawnMovementComponent",
    "Runtime/Engine/UInputComponent",
    "Runtime/Engine/UPlayerInput",
    # Assets / content
    "Runtime/Engine/UAssetManager",
    "Runtime/Engine/UObjectLibrary",
    "Runtime/Engine/UMaterial",
    "Runtime/Engine/UMaterialInstance",
    "Runtime/Engine/UMaterialInstanceDynamic",
    "Runtime/Engine/UMaterialInterface",
    "Runtime/Engine/UTexture2D",
    "Runtime/Engine/UStaticMesh",
    "Runtime/Engine/UStaticMeshComponent",
    "Runtime/Engine/USkeletalMesh",
    "Runtime/Engine/USkeletalMeshComponent",
    "Runtime/Engine/UAnimInstance",
    "Runtime/Engine/UAnimMontage",
    "Runtime/Engine/UDataTable",
    "Runtime/Engine/UDataAsset",
    "Runtime/Engine/UBlueprint",
    "Runtime/Engine/UWorldSubsystem",
    "Runtime/Engine/UGameInstanceSubsystem",
    "Runtime/UMG/UUserWidget",
    "Runtime/UMG/UWidgetBlueprintLibrary",
    "Runtime/Engine/UCameraComponent",
    "Runtime/Engine/USpringArmComponent",
    "Runtime/Engine/USoundBase",
    "Runtime/Engine/UAudioComponent",
    "Runtime/Engine/UParticleSystem",
    "Runtime/Engine/ULightComponent",
    "Runtime/Engine/UPhysicsHandleComponent",
    "Runtime/UMG/UCanvasPanelSlot",
    "Runtime/UMG/UUserWidget",
    # AI / navigation
    "Runtime/AIModule/AAIController",
    "Runtime/AIModule/UBehaviorTreeComponent",
    "Runtime/NavigationSystem/UNavigationSystemV1",
    # Rendering
    "Runtime/RHI/FRHIResource",
]


def main():
    os.makedirs(OUT, exist_ok=True)
    pages = {}
    if os.path.exists(INDEX):
        try:
            pages = json.load(open(INDEX, encoding="utf-8")).get("pages") or {}
        except Exception:
            pages = {}

    ok = 0
    miss = 0
    for path in PRIORITY:
        if path in pages:
            continue
        html = fetch_html(path)
        if not html:
            print(f"  MISS {path}")
            miss += 1
            continue
        body = html_to_text(html)
        if len(body) < 800:
            print(f"  THIN {path} ({len(body)} chars)")
            miss += 1
            continue
        title_m = re.search(r"<title>([^<]*)</title>", html)
        title = (title_m.group(1).split("|")[0].strip() if title_m
                 else path.split("/")[-1])
        fn = safe(path) + ".md"
        url = f"{BASE_DOC}/{ROOT}/API/{path}"
        with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n> Source: {url}\n"
                    f"> Unreal Engine 5.8 C++ API\n\n---\n\n{body}\n")
        pages[path] = {"title": title, "file": fn, "url": url,
                       "category": path.split("/")[0], "size": len(body)}
        ok += 1
        print(f"  OK   {path} ({len(body)} chars)")

    json.dump({"pages": pages}, open(INDEX, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\npriority fetch: ok={ok} miss={miss} total={len(pages)}")


if __name__ == "__main__":
    main()
