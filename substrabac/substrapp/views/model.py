import os
import tempfile
import logging
import requests
from django.http import Http404
from rest_framework import status, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from substrapp.models import Model
from substrapp.serializers import ModelSerializer

from substrapp.utils import JsonException
from substrapp.ledger_utils import queryLedger, getObjectFromLedger
from substrapp.views.utils import ComputeHashMixin, CustomFileResponse, validate_pk
from substrapp.views.filters import filter_list


class ModelViewSet(mixins.RetrieveModelMixin,
                   mixins.ListModelMixin,
                   ComputeHashMixin,
                   GenericViewSet):
    queryset = Model.objects.all()
    serializer_class = ModelSerializer
    ledger_query_call = 'queryModelDetails'

    # permission_classes = (permissions.IsAuthenticated,)

    def create_or_update_model(self, traintuple, pk):
        if traintuple['outModel'] is None:
            raise Exception(f'This traintuple related to this model key {pk} does not have a outModel')

        # Get model from remote node
        url = traintuple['outModel']['storageAddress']
        try:
            r = requests.get(url, headers={'Accept': 'application/json;version=0.0'})
        except Exception:
            raise Exception(f'Failed to fetch {url}')
        else:
            if r.status_code != 200:
                raise Exception(f'end to end node report {r.text}')

        # Verify model received has a good pkhash
        try:
            computed_hash = self.compute_hash(r.content, traintuple['key'])
        except Exception:
            raise Exception('Failed to fetch outModel file')
        else:
            if computed_hash != pk:
                msg = 'computed hash is not the same as the hosted file. ' \
                      'Please investigate for default of synchronization, corruption, or hacked'
                raise Exception(msg)

        # Write model in local db for later use
        tmp_model = tempfile.TemporaryFile()
        tmp_model.write(r.content)
        instance, created = Model.objects.update_or_create(pkhash=pk, validated=True)
        instance.file.save('model', tmp_model)

        return instance

    def retrieve(self, request, *args, **kwargs):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        pk = self.kwargs[lookup_url_kwarg]

        try:
            validate_pk(pk)
        except Exception as e:
            return Response({'message': str(e)}, status.HTTP_400_BAD_REQUEST)

        # get instance from remote node
        try:
            data = getObjectFromLedger(pk, self.ledger_query_call)
        except JsonException as e:
            return Response(e.msg, status=status.HTTP_400_BAD_REQUEST)
        except Http404:
            return Response(f'No element with key {pk}', status=status.HTTP_404_NOT_FOUND)
        else:
            # Try to get it from local db, else create it in local db
            try:
                instance = self.get_object()
            except Http404:
                try:
                    instance = self.create_or_update_model(data['traintuple'],
                                                           data['traintuple']['outModel']['hash'])
                except Exception as e:
                    Response({'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            else:
                if not instance.file:
                    try:
                        instance = self.create_or_update_model(data['traintuple'],
                                                               data['traintuple']['outModel']['hash'])
                    except Exception as e:
                        Response({'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)

            # For security reason, do not give access to local file address
            # Restrain data to some fields
            # TODO: do we need to send creation date and/or last modified date
            serializer = self.get_serializer(instance, fields=('owner', 'pkhash'))
            data.update(serializer.data)

            return Response(data, status=status.HTTP_200_OK)

    def list(self, request, *args, **kwargs):

        data, st = queryLedger(fcn='queryModels', args=[])
        data = data if data else []

        models_list = [data]

        if st == status.HTTP_200_OK:
            # parse filters
            query_params = request.query_params.get('search', None)

            if query_params is not None:
                try:
                    models_list = filter_list(
                        object_type='model',
                        data=data,
                        query_params=query_params)
                except Exception as e:
                    logging.exception(e)
                    return Response(
                        {'message': f'Malformed search filters {query_params}'},
                        status=status.HTTP_400_BAD_REQUEST)

        return Response(models_list, status=st)

    @action(detail=True)
    def file(self, request, *args, **kwargs):
        model_object = self.get_object()
        data = getattr(model_object, 'file')
        return CustomFileResponse(open(data.path, 'rb'), as_attachment=True, filename=os.path.basename(data.path))

    @action(detail=True)
    def details(self, request, *args, **kwargs):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        pk = self.kwargs[lookup_url_kwarg]
        data, st = queryLedger(fcn='queryModelDetails', args=[f'{pk}'])
        return Response(data, st)
