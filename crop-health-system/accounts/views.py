from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import redirect, render

from farms.models import CropCycle, Farm
from .models import Profile


MAHARASHTRA_DISTRICTS = [
    "Ahmednagar", "Akola", "Amravati", "Aurangabad", "Beed", "Bhandara",
    "Buldhana", "Chandrapur", "Dhule", "Gadchiroli", "Gondia", "Hingoli",
    "Jalgaon", "Jalna", "Kolhapur", "Latur", "Mumbai City", "Mumbai Suburban",
    "Nagpur", "Nanded", "Nandurbar", "Nashik", "Osmanabad", "Palghar",
    "Parbhani", "Pune", "Raigad", "Ratnagiri", "Sangli", "Satara",
    "Sindhudurg", "Solapur", "Thane", "Wardha", "Washim", "Yavatmal",
]

CROPS = [
    "Tomato", "Potato", "Corn (Maize)", "Grape", "Sugarcane", "Cotton",
    "Onion", "Soybean", "Wheat", "Rice", "Groundnut", "Banana",
]


def register_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:farmer_home")

    errors = {}
    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name  = request.POST.get("last_name", "").strip()
        username   = request.POST.get("username", "").strip()
        phone      = request.POST.get("phone", "").strip()
        district   = request.POST.get("district", "").strip()
        taluka     = request.POST.get("taluka", "").strip()
        language   = request.POST.get("language", "en")
        crop       = request.POST.get("crop", "").strip()
        area_acres = request.POST.get("area_acres", "").strip()
        password1  = request.POST.get("password1", "")
        password2  = request.POST.get("password2", "")

        if not first_name:
            errors["first_name"] = "First name is required."
        if not username:
            errors["username"] = "Username is required."
        elif User.objects.filter(username=username).exists():
            errors["username"] = "This username is already taken."
        if not phone:
            errors["phone"] = "Phone number is required."
        if not district:
            errors["district"] = "District is required."
        if not password1:
            errors["password1"] = "Password is required."
        elif len(password1) < 6:
            errors["password1"] = "Password must be at least 6 characters."
        elif password1 != password2:
            errors["password2"] = "Passwords do not match."

        if not errors:
            user = User.objects.create_user(
                username=username,
                password=password1,
                first_name=first_name,
                last_name=last_name,
                email=f"{username}@krishi.mh.gov.in",
            )
            Profile.objects.update_or_create(
                user=user,
                defaults={
                    "role": Profile.Role.FARMER,
                    "phone": phone,
                    "district": district,
                    "taluka": taluka,
                    "preferred_language": language,
                },
            )
            # Auto-create a default farm so they can scan immediately
            if district:
                import random
                DISTRICT_COORDS = {
                    "Pune": (18.5204, 73.8567), "Nashik": (19.9975, 73.7898),
                    "Jalgaon": (21.0077, 75.5626), "Aurangabad": (19.8762, 75.3433),
                    "Nagpur": (21.1458, 79.0882), "Kolhapur": (16.6949, 74.2310),
                    "Solapur": (17.6805, 75.3214), "Ahmednagar": (19.0952, 74.7496),
                }
                lat, lng = DISTRICT_COORDS.get(district, (19.5, 75.5))
                farm_name = f"{last_name or first_name}'s Farm"
                farm = Farm.objects.create(
                    owner=user,
                    name=farm_name,
                    latitude=lat,
                    longitude=lng,
                    area_acres=float(area_acres) if area_acres else 2.0,
                    district=district,
                    taluka=taluka,
                )
                if crop:
                    import datetime
                    CropCycle.objects.create(
                        farm=farm,
                        crop=crop,
                        sowing_date=datetime.date.today(),
                        growth_stage=CropCycle.GrowthStage.VEGETATIVE,
                    )

            login(request, user)
            return redirect("accounts:farmer_home")

    return render(request, "accounts/register.html", {
        "errors": errors,
        "post": request.POST,
        "districts": MAHARASHTRA_DISTRICTS,
        "crops": CROPS,
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:farmer_home")

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            next_url = request.GET.get("next") or (
                "dashboard:index" if user.is_staff else "accounts:farmer_home"
            )
            return redirect(next_url)
        error = "Invalid username or password."

    return render(request, "accounts/login.html", {"error": error})


def logout_view(request):
    logout(request)
    return redirect("accounts:login")


@login_required
def farmer_home(request):
    from reports.models import DiseaseReport
    reports = DiseaseReport.objects.filter(farmer=request.user).select_related("farm").order_by("-created_at")[:10]
    farms = Farm.objects.filter(owner=request.user)
    return render(request, "accounts/farmer_home.html", {
        "reports": reports,
        "farms": farms,
    })
